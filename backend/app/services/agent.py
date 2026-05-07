"""Anthropic agent — the brain behind the Zalo bot.

Calls Claude Haiku 4.5 via the Messages API with the *native MCP connector*:
Claude reaches our deployed `/mcp/` endpoint server-side, calls our tools,
loops until done, and returns the final Vietnamese reply text.

System prompt is composed of two blocks:
  1. The shared Vietnamese template from AGENT_PROMPT.md (cached — every
     turn re-uses the prefix; cache_control: ephemeral).
  2. A short per-turn dynamic block carrying org_id + user role. Not
     cached on purpose: it's small, and varies per Zalo user / org.

The dynamic block tells Claude *which* org_id to pass to every MCP tool
call. The MCP server doesn't enforce org context (it trusts the bearer
token), so the prompt is what makes routing right.
"""

from __future__ import annotations

import logging
from pathlib import Path

from anthropic import AsyncAnthropic

from app.config import get_settings
from app.services.zalo_attachments import ImageInput

log = logging.getLogger(__name__)

MCP_BETA = "mcp-client-2025-04-04"
PROMPT_PATH = Path(__file__).parent / "AGENT_PROMPT.md"


def _load_system_prompt() -> str:
    raw = PROMPT_PATH.read_text(encoding="utf-8")
    if "```" in raw:
        parts = raw.split("```")
        body = parts[1]
        if body.lstrip().startswith(("text\n", "markdown\n")):
            body = body.split("\n", 1)[1]
        return body.strip()
    return raw.strip()


_SYSTEM_PROMPT: str | None = None


def system_prompt() -> str:
    global _SYSTEM_PROMPT
    if _SYSTEM_PROMPT is None:
        _SYSTEM_PROMPT = _load_system_prompt()
    return _SYSTEM_PROMPT


def _session_context(
    org_id: str,
    user_role: str,
    display_name: str | None,
    zalo_id: str,
    onboarding_step: str | None = None,
    image_unavailable: bool = False,
) -> str:
    """The short per-turn block that names the org, the caller's Zalo id,
    and tells Claude to thread `org_id` through every MCP tool call.
    For admins, also nudges Claude toward the access-request tools.
    For users mid-onboarding, injects step-specific instructions."""
    name = display_name or "Anh/Chị"
    base = (
        "## Bối cảnh phiên hiện tại\n\n"
        f"Người dùng: {name} (vai trò: {user_role}, zalo_id: `{zalo_id}`).\n"
        f"Tổ chức (org_id): `{org_id}`.\n\n"
        "QUAN TRỌNG: Khi gọi bất cứ tool nào (get_product, get_inventory, "
        "create_import_invoice, confirm_action, …), LUÔN truyền tham số "
        f"`org_id=\"{org_id}\"`. Đây là tham số bắt buộc."
    )
    if onboarding_step == "garage_profile":
        base += (
            "\n\n## ĐANG ONBOARD — Bước 1/2: Thông tin tiệm\n\n"
            "Người dùng vừa được duyệt vào hệ thống và CHƯA hoàn tất setup. "
            "Dẫn dắt từng bước, hỏi LẦN LƯỢT từng câu một, mỗi tin nhắn 1 câu hỏi:\n"
            "1. Địa chỉ tiệm? (gợi ý: '123 Nguyễn Huệ, Q.1, TP.HCM')\n"
            "2. Số điện thoại tiệm? (gợi ý: 'Anh có thể gửi luôn số Zalo đăng ký')\n"
            "3. Mã số thuế? (tùy chọn — anh có thể gửi 'bỏ qua')\n\n"
            "Sau MỖI câu trả lời: gọi `update_org_info(org_id, address=...)` "
            "(hoặc phone, tax_id tương ứng), rồi hỏi câu tiếp theo.\n"
            "Khi hỏi xong cả 3 (kể cả nếu bỏ qua tax_id): gọi "
            f"`set_onboarding_step(zalo_id=\"{zalo_id}\", step=\"first_inventory\")` "
            "RỒI chuyển sang bước 2 với tin nhắn:\n"
            "  'Tiệm đã sẵn sàng. Giờ anh nhập 1-2 sản phẩm/dịch vụ chính, "
            "  dạng \"Tên - giá\" mỗi dòng. Ví dụ:\n"
            "    Dầu nhớt Castrol 5W30 - 250k\n"
            "    Lọc dầu Toyota - 80k\n"
            "    Công thay nhớt - 50k'\n\n"
            "Nếu người dùng nói 'bỏ qua hết' hoặc 'lát em làm sau': gọi "
            f"`set_onboarding_step(zalo_id=\"{zalo_id}\", step=\"done\")` và "
            "trả lời 'OK, anh có thể setup sau qua trang quản lý web.'"
        )
    elif onboarding_step == "first_inventory":
        base += (
            "\n\n## ĐANG ONBOARD — Bước 2/2: Sản phẩm/Dịch vụ ban đầu\n\n"
            "Người dùng đang nhập danh sách sản phẩm/dịch vụ đầu tiên.\n"
            "Quy tắc xử lý:\n"
            "  - Parse từng dòng dạng 'Tên - giá' thành (name, selling_price). "
            "Hỗ trợ '250k' = 250000, '1.5tr' = 1500000, '200000đ' = 200000.\n"
            "  - Nếu một dòng không parse được, HỎI LẠI cụ thể dòng đó: "
            "'Em chưa hiểu dòng <X>, anh viết lại theo dạng \"Tên - giá\" giúp em.'\n"
            "  - Khi parse được: gọi `add_product(org_id, name, selling_price)` "
            "cho từng dòng, gom các preview_id, đọc lại danh sách cho user "
            "xác nhận, rồi gọi `confirm_action(org_id, preview_id)` cho từng cái.\n"
            "  - Sau khi tạo xong (hoặc người dùng nói 'lát em nhập sau' / "
            "'bỏ qua'): gọi "
            f"`set_onboarding_step(zalo_id=\"{zalo_id}\", step=\"done\")` "
            "và đọc câu chốt:\n"
            "  'Hoàn tất setup. Anh có thể: tạo hóa đơn, kiểm kho, xem báo cáo, "
            "hoặc nhắn \"đăng nhập web\" để mở trang quản lý. Cần gì cứ nhắn em.'"
        )
    if image_unavailable:
        base += (
            "\n\n## NOTE: Người dùng vừa gửi ẢNH nhưng hệ thống không tải được\n\n"
            "Zalo CDN chặn truy cập từ máy chủ ngoài Việt Nam — đây là "
            "giới hạn của Zalo, không phải lỗi của bạn. KHÔNG hỏi người "
            "dùng mô tả bằng chữ — thay vào đó BẮT BUỘC làm như sau:\n"
            f"1. Gọi `get_upload_url(zalo_id=\"{zalo_id}\")` để lấy link "
            "upload web (30 phút).\n"
            "2. Trả lời ngắn gọn kèm link:\n"
            "  'Em chưa xem được ảnh anh gửi (Zalo chặn). Anh upload qua "
            "link này (30 phút): <url> — chọn ảnh + ghi chú nếu cần. Em "
            "sẽ phân tích và gửi kết quả về Zalo.'\n"
            "Chỉ gửi nguyên link, KHÔNG markdown link wrapper.\n\n"
            "Nếu caption ảnh có nội dung rõ (ví dụ 'còn dầu Castrol 5W30 "
            "không'), xử lý nội dung caption trước, rồi kèm link upload "
            "phía sau cho lần khác."
        )

    if user_role == "admin":
        base += (
            "\n\n## Anh là ADMIN của hệ thống\n\n"
            "Bot có thể chuyển yêu cầu truy cập từ người dùng mới vào DM "
            "của anh dưới dạng:\n"
            "  '🆕 Yêu cầu mới: <tên> (zalo:<id>) … Mã yêu cầu: <request_id> …'\n\n"
            "Khi anh trả lời ý định duyệt/từ chối:\n"
            "  - Duyệt vào tiệm CÓ SẴN: gọi `approve_access_request(request_id=..., "
            "target_org_id=<slug>, role=<owner|manager|member>, "
            f"admin_zalo_id=\"{zalo_id}\")`.\n"
            "  - Duyệt + tạo tiệm MỚI (anh nói 'duyệt 12345 tạo tiệm <tên> "
            "cho ảnh làm chủ'): gọi `create_organization(name=<tên>, "
            f"admin_zalo_id=\"{zalo_id}\")` để lấy slug, RỒI gọi "
            "`approve_access_request(...)` với role='owner' và slug vừa lấy.\n"
            "  - Từ chối: gọi `deny_access_request(request_id=..., reason=<lý do>, "
            f"admin_zalo_id=\"{zalo_id}\")`.\n"
            "  - Liệt kê yêu cầu đang chờ: `list_pending_access_requests()`.\n\n"
            "QUAN TRỌNG — chào mừng người dùng vừa duyệt:\n"
            "Nếu `approve_access_request` trả về `needs_onboarding: true` "
            "(người dùng là owner đầu tiên của một tiệm chưa setup), gọi "
            "`send_dm(zalo_id=<zalo_id của người dùng vừa duyệt>, text=<lời chào>)` "
            "để khởi động onboarding ở chat của người đó. Nội dung text đại "
            "loại: 'Chào anh, em là trợ lý quản lý tiệm. Em đã được phép "
            "giúp anh quản lý <tên tiệm>. Trước hết, em cần một số thông "
            "tin để in trên hóa đơn — Địa chỉ tiệm của anh là gì ạ?'\n\n"
            "Nếu `needs_onboarding: false`, chỉ trả lời cho admin là đã "
            "duyệt, KHÔNG gọi send_dm.\n\n"
            "Đối với các tool quản trị này KHÔNG cần truyền org_id — "
            "chúng hoạt động ở phạm vi toàn hệ thống."
        )
    return base


_client: AsyncAnthropic | None = None


def _get_client() -> AsyncAnthropic:
    global _client
    if _client is None:
        settings = get_settings()
        if not settings.anthropic_api_key:
            raise RuntimeError("ANTHROPIC_API_KEY unset")
        _client = AsyncAnthropic(api_key=settings.anthropic_api_key)
    return _client


async def reply(
    user_text: str,
    *,
    org_id: str,
    user_role: str = "member",
    user_display_name: str | None = None,
    history: list[dict] | None = None,
    zalo_id: str = "",
    image: ImageInput | None = None,
    pdf_bytes: bytes | None = None,
    onboarding_step: str | None = None,
    image_unavailable: bool = False,
) -> tuple[str, list[dict]]:
    """Run one Zalo turn through Claude + MCP.

    Returns `(final_text, assistant_content_blocks)`. Caller is expected to
    persist `user_text` as a user turn and `assistant_content_blocks` as
    the matching assistant turn so two-phase confirms (preview → user "ok" →
    confirm) work across Zalo messages.

    `image` is optional — when set, prepended as an image content block
    so Claude (vision-capable) can analyze the photo alongside any caption.
    """
    settings = get_settings()
    client = _get_client()

    import base64 as _b64

    messages: list[dict] = list(history or [])
    if not user_text and image is None and pdf_bytes is None:
        # Empty content would 400 from Anthropic. Inject a minimal
        # placeholder so the session_context's image_unavailable note
        # is what drives the reply.
        if image_unavailable:
            user_text = "(người dùng gửi ảnh)"

    user_content: list[dict] = []
    if image is not None:
        # Anthropic's image content block — base64 source so we don't
        # depend on Zalo CDN URLs being reachable from Anthropic's side.
        user_content.append({
            "type": "image",
            "source": {
                "type": "base64",
                "media_type": image.mime,
                "data": image.b64,
            },
        })
    if pdf_bytes is not None:
        user_content.append({
            "type": "document",
            "source": {
                "type": "base64",
                "media_type": "application/pdf",
                "data": _b64.b64encode(pdf_bytes).decode(),
            },
        })
    if user_content:
        # Always include a text block — Anthropic accepts image/document
        # blocks alongside text, but a content list with only attachments
        # gets cleaner results when paired with at least a placeholder.
        user_content.append(
            {"type": "text", "text": user_text or "(người dùng gửi tệp đính kèm)"}
        )
        messages.append({"role": "user", "content": user_content})
    else:
        messages.append({"role": "user", "content": user_text})

    resp = await client.beta.messages.create(
        model=settings.agent_model,
        max_tokens=1024,
        system=[
            {
                "type": "text",
                "text": system_prompt(),
                "cache_control": {"type": "ephemeral"},
            },
            {
                "type": "text",
                "text": _session_context(
                    org_id,
                    user_role,
                    user_display_name,
                    zalo_id,
                    onboarding_step,
                    image_unavailable,
                ),
            },
        ],
        messages=messages,
        mcp_servers=[
            {
                "type": "url",
                "url": settings.mcp_self_url,
                "name": "garage-ai",
                "authorization_token": settings.openclaw_api_key,
            }
        ],
        betas=[MCP_BETA],
    )

    # Persist the FULL block list (preamble + tool_use + tool_result + answer)
    # so the next turn replays complete context to Claude. But only forward
    # to Zalo the text that comes *after* the last tool call — anything
    # before that is the model thinking out loud ("Cho mình tìm khách…")
    # and just adds noise in chat.
    content_blocks: list[dict] = []
    last_tool_idx = -1
    mcp_calls = 0
    for i, block in enumerate(resp.content):
        block_dict = (
            block.model_dump(mode="json") if hasattr(block, "model_dump") else dict(block)
        )
        content_blocks.append(block_dict)
        btype = getattr(block, "type", None)
        if btype in ("mcp_tool_use", "tool_use"):
            mcp_calls += 1
            last_tool_idx = i

    text_parts: list[str] = []
    for i, block in enumerate(resp.content):
        if i <= last_tool_idx:
            continue
        if getattr(block, "type", None) == "text":
            text_parts.append(block.text)

    final_text = "\n\n".join(p.strip() for p in text_parts if p.strip())
    log.info(
        "agent: org=%s role=%s model=%s stop=%s mcp_calls=%d reply_chars=%d history=%d",
        org_id,
        user_role,
        settings.agent_model,
        getattr(resp, "stop_reason", "?"),
        mcp_calls,
        len(final_text),
        len(history or []),
    )

    if not final_text:
        final_text = "Xin lỗi, em đang gặp lỗi. Anh thử lại sau nhé."
    return final_text, content_blocks
