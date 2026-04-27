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
) -> str:
    """The short per-turn block that names the org, the caller's Zalo id,
    and tells Claude to thread `org_id` through every MCP tool call.
    For admins, also nudges Claude toward the access-request tools."""
    name = display_name or "Anh/Chị"
    base = (
        "## Bối cảnh phiên hiện tại\n\n"
        f"Người dùng: {name} (vai trò: {user_role}, zalo_id: `{zalo_id}`).\n"
        f"Tổ chức (org_id): `{org_id}`.\n\n"
        "QUAN TRỌNG: Khi gọi bất cứ tool nào (get_product, get_inventory, "
        "create_import_invoice, confirm_action, …), LUÔN truyền tham số "
        f"`org_id=\"{org_id}\"`. Đây là tham số bắt buộc."
    )
    if user_role == "admin":
        base += (
            "\n\n## Anh là ADMIN của hệ thống\n\n"
            "Bot có thể chuyển yêu cầu truy cập từ người dùng mới vào DM "
            "của anh dưới dạng:\n"
            "  '🆕 Yêu cầu mới: <tên> (zalo:<id>) … Mã yêu cầu: <request_id> …'\n\n"
            "Khi anh trả lời ý định duyệt/từ chối:\n"
            "  - Duyệt: gọi `approve_access_request(request_id=..., "
            "target_org_id=<slug>, role=<owner|manager|member>, "
            f"admin_zalo_id=\"{zalo_id}\")`. Sau khi tool trả về OK, đọc lại "
            "kết quả cho anh bằng tiếng Việt.\n"
            "  - Từ chối: gọi `deny_access_request(request_id=..., reason=<lý do>, "
            f"admin_zalo_id=\"{zalo_id}\")`.\n"
            "  - Liệt kê yêu cầu đang chờ: `list_pending_access_requests()`.\n"
            "  - Tạo tổ chức mới: `create_organization(name=<tên>, "
            f"admin_zalo_id=\"{zalo_id}\")`.\n\n"
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
) -> tuple[str, list[dict]]:
    """Run one Zalo turn through Claude + MCP.

    Returns `(final_text, assistant_content_blocks)`. Caller is expected to
    persist `user_text` as a user turn and `assistant_content_blocks` as
    the matching assistant turn so two-phase confirms (preview → "ok" →
    confirm) work across Zalo messages.
    """
    settings = get_settings()
    client = _get_client()

    messages: list[dict] = list(history or [])
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
                "text": _session_context(org_id, user_role, user_display_name, zalo_id),
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
