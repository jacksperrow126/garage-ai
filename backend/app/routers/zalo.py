"""Zalo Bot webhook.

Zalo POSTs to this endpoint on every event. We:
  1. verify the static webhook secret in the X-Bot-Api-Secret-Token header
  2. allowlist by sender's Zalo user id
  3. dedupe by message_id (Zalo retries on non-200)
  4. respond 200 immediately and run the LLM + reply in a background task
     (Zalo's webhook timeout is short; LLM call takes seconds)

Per Zalo docs the envelope is:
  {"ok": true, "result": {"event_name": "...", "message": {...}}}

We only handle `message.text.received` for now; other events are 200-acked.
"""

from __future__ import annotations

import hmac
import logging
from typing import Any

from fastapi import APIRouter, BackgroundTasks, Header, HTTPException, Request, status
from google.cloud.firestore import Client

from app.config import get_settings
from app.firestore import get_db, server_timestamp
from app.services import (
    access_requests,
    agent,
    conversation,
    zalo_attachments,
    zalo_client,
    zalo_users,
)

log = logging.getLogger(__name__)

router = APIRouter()


def _verify_secret(presented: str | None) -> None:
    expected = get_settings().zalo_webhook_secret
    if not expected:
        # Fail closed if misconfigured rather than accept everything.
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "webhook secret not configured")
    if not presented or not hmac.compare_digest(presented, expected):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "invalid webhook secret")


def _claim_message(db: Client, message_id: str) -> bool:
    """Return True if this is the first time we've seen this message_id.

    Zalo retries on 5xx (and on timeouts), so without dedupe a single user
    message can fire two LLM calls + two replies. We use the message_id as
    the doc key in `zalo_messages_seen` and rely on .create() raising on
    a pre-existing doc."""
    ref = db.collection("zalo_messages_seen").document(message_id)
    try:
        ref.create({"created_at": server_timestamp()})
        return True
    except Exception:  # google.api_core.exceptions.AlreadyExists or similar
        return False


async def _onboard_unknown_sender(
    user_id: str, chat_id: str, text: str, display_name: str | None
) -> None:
    """Unknown senders → create (or surface existing) access request,
    DM the admin(s), reply to the requester with a brief acknowledgement."""
    request, is_new = access_requests.create_or_get_pending(
        user_id, display_name, text
    )
    if not is_new:
        await zalo_client.send_message(
            chat_id,
            "Yêu cầu của anh đang chờ admin duyệt. Em sẽ báo lại khi có kết quả.",
        )
        return

    await zalo_client.send_message(
        chat_id,
        "Em đã chuyển yêu cầu cấp quyền của anh cho admin. "
        "Khi được duyệt em sẽ báo lại ngay.",
    )

    admins = access_requests.list_admins()
    name = display_name or "Người dùng"
    notice = (
        f"🆕 Yêu cầu mới: {name} (zalo:{user_id}) muốn dùng dịch vụ.\n\n"
        f"Tin nhắn: \"{text}\"\n\n"
        f"Mã yêu cầu: {request['id']}\n\n"
        "Để duyệt, anh có thể trả lời (ví dụ): "
        f"'duyệt {request['id']} cho tiệm garage-chinh vai trò manager'.\n"
        f"Để từ chối: 'từ chối {request['id']} lý do <ngắn gọn>'."
    )
    for admin in admins:
        admin_chat_id = admin["id"]  # for Zalo, private chat_id == user id
        try:
            await zalo_client.send_message(admin_chat_id, notice)
        except Exception as exc:
            log.exception("zalo: failed to DM admin %s: %s", admin_chat_id, exc)


async def _process_message(
    user_id: str,
    chat_id: str,
    text: str,
    display_name: str | None,
    image_urls: list[str] | None = None,
) -> None:
    """Background task: look up the sender, route to the agent, send the reply.

    Errors are logged but never re-raised — we've already 200-acked the
    webhook, and crashing here just produces a Cloud Run error log without
    helping the user. We do try to send a polite Vietnamese error reply.

    `image_urls`, if non-empty, contains image attachment URLs from the
    webhook envelope. We download the first one and pass it to the agent
    as a vision input alongside the text caption."""
    user = zalo_users.get(user_id)

    if not user or not user.get("primary_org_id"):
        await _onboard_unknown_sender(
            user_id, chat_id, text or "(người dùng gửi ảnh)", display_name
        )
        return

    org_id = user["primary_org_id"]
    user_role = user.get("system_role") or "member"
    display = user.get("name") or display_name
    onboarding_step = user.get("onboarding_step")

    image: zalo_attachments.ImageInput | None = None
    image_unavailable = False
    if image_urls:
        image = await zalo_attachments.download_image(image_urls[0])
        if image is None:
            # Zalo CDN routinely blocks non-VN egress — Cloud Run can't
            # fetch the bytes. Tell the agent so it asks the user to
            # describe the photo in text instead of silently dropping.
            image_unavailable = True

    # What we persist as the user-turn text. Bytes themselves aren't
    # round-tripped through history (cost + Firestore 1MB doc cap) —
    # a placeholder lets future turns know an image was sent.
    persisted_text = (
        f"[ảnh] {text}" if (image and text) else
        "[ảnh đính kèm]" if image else
        f"[ảnh không tải được] {text}" if (image_unavailable and text) else
        "[ảnh không tải được]" if image_unavailable else
        text
    )

    history = conversation.load(user_id)
    assistant_content: list[dict] | None = None
    try:
        reply_text, assistant_content = await agent.reply(
            text,
            org_id=org_id,
            user_role=user_role,
            user_display_name=display,
            history=history,
            zalo_id=user_id,
            image=image,
            onboarding_step=onboarding_step,
            image_unavailable=image_unavailable,
        )
    except Exception as exc:
        log.exception("agent.reply failed: %s", exc)
        reply_text = "Xin lỗi, em đang gặp lỗi. Anh thử lại sau nhé."

    try:
        await zalo_client.send_message(chat_id, reply_text)
    except Exception as exc:
        log.exception("zalo send failed: %s", exc)

    # Only persist successful turns. On error we want the user's next message
    # to start fresh rather than re-trigger Claude on a broken state.
    if assistant_content is not None:
        try:
            conversation.append_turn(user_id, persisted_text, assistant_content)
        except Exception as exc:
            log.exception("conversation persist failed: %s", exc)


@router.post("/webhook")
async def webhook(
    request: Request,
    bg: BackgroundTasks,
    x_bot_api_secret_token: str | None = Header(default=None),
) -> dict[str, str]:
    _verify_secret(x_bot_api_secret_token)

    body: dict[str, Any] = await request.json()
    result = body.get("result") or {}
    event_name = result.get("event_name") or body.get("event_name") or ""
    message = result.get("message") or body.get("message") or {}

    # Recognized: text, and any event whose envelope carries an image
    # attachment we know how to extract. Anything else is 200-acked
    # (Zalo's webhook timeout retries on 5xx) but logged so we can
    # extend coverage when we see new event names.
    image_urls = zalo_attachments.extract_image_urls(message)
    is_text = event_name == "message.text.received"
    is_image = bool(image_urls) or any(
        kw in event_name for kw in ("image", "photo", "attachment", "media")
    )

    if not (is_text or is_image):
        log.info("zalo: ignoring event %r body=%r", event_name, body)
        return {"message": "Success"}

    if is_image and not image_urls:
        # Event name suggested an image but we couldn't pull a URL out.
        # Log loud so we know what path to add to extract_image_urls.
        log.warning(
            "zalo: image-shaped event %r but no URL found. body=%r",
            event_name,
            body,
        )

    sender = (message.get("from") or {}).get("id") or ""
    display_name = (message.get("from") or {}).get("display_name") or None
    chat_id = (message.get("chat") or {}).get("id") or sender
    # Image messages may carry a caption in `caption` (or `text`).
    text = message.get("text") or message.get("caption") or ""
    message_id = message.get("message_id") or ""

    if not (sender and chat_id and message_id) or not (text or image_urls):
        log.warning("zalo: malformed message envelope: %s", body)
        return {"message": "Success"}

    if not _claim_message(get_db(), message_id):
        log.info("zalo: duplicate message_id %s — skipping", message_id)
        return {"message": "Success"}

    log.info(
        "zalo: dispatching turn from %s (msg=%s images=%d)",
        sender,
        message_id,
        len(image_urls),
    )
    bg.add_task(_process_message, sender, chat_id, text, display_name, image_urls)
    return {"message": "Success"}
