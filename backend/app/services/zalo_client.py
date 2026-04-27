"""Zalo Bot send-message client.

Talks to bot-api.zaloplatforms.com/bot{TOKEN}/<method>. The bot token is
embedded in the URL path (Telegram-style); no Authorization header needed.

Per Zalo docs, sendMessage caps text at 2000 chars — longer replies are
split on paragraph / sentence boundaries.

Zalo chat is plain-text only — no markdown rendering. Any `**bold**` /
`*italic*` / `# heading` / `` `code` `` produced by the LLM has to be
stripped here, otherwise the user sees the literal markup characters.
"""

from __future__ import annotations

import logging
import re

import httpx

from app.config import get_settings

log = logging.getLogger(__name__)

ZALO_BASE = "https://bot-api.zaloplatforms.com"
MAX_LEN = 2000

# Strip in this order: bold (`**x**`, `__x__`) before italic (`*x*`, `_x_`)
# so we don't half-eat a `**`. Inline code last; headers separately.
_BOLD = re.compile(r"\*\*(.+?)\*\*", re.DOTALL)
_BOLD_UNDERSCORE = re.compile(r"__(.+?)__", re.DOTALL)
_ITALIC_STAR = re.compile(r"(?<!\*)\*([^*\n]+?)\*(?!\*)")
_INLINE_CODE = re.compile(r"`([^`\n]+?)`")
_HEADER = re.compile(r"^\s*#{1,6}\s+", re.MULTILINE)


def strip_markdown(text: str) -> str:
    """Remove the markdown formatting Claude tends to emit. Keep newlines,
    list numbers (`1. foo`), and emojis — those render fine in Zalo."""
    text = _BOLD.sub(r"\1", text)
    text = _BOLD_UNDERSCORE.sub(r"\1", text)
    text = _ITALIC_STAR.sub(r"\1", text)
    text = _INLINE_CODE.sub(r"\1", text)
    text = _HEADER.sub("", text)
    return text


def _split(text: str, limit: int = MAX_LEN) -> list[str]:
    """Split text into chunks ≤ limit, preferring paragraph then sentence
    boundaries. Pure-ASCII length is fine here — Zalo's limit is char-based,
    not byte-based, so Vietnamese diacritics each count as one char."""
    if len(text) <= limit:
        return [text]

    chunks: list[str] = []
    remaining = text
    while len(remaining) > limit:
        # Prefer the last paragraph break before the limit.
        cut = remaining.rfind("\n\n", 0, limit)
        if cut < limit // 2:
            cut = remaining.rfind("\n", 0, limit)
        if cut < limit // 2:
            cut = remaining.rfind(". ", 0, limit)
        if cut < limit // 2:
            cut = limit  # hard cut as last resort
        chunks.append(remaining[:cut].rstrip())
        remaining = remaining[cut:].lstrip()
    if remaining:
        chunks.append(remaining)
    return chunks


async def send_message(chat_id: str, text: str) -> None:
    """Send one (or more, if split) text messages to a Zalo chat.

    Errors are logged but not raised — a failed reply shouldn't crash the
    webhook handler. The user notices the missing reply, which is the
    right signal."""
    settings = get_settings()
    if not settings.zalo_bot_token:
        log.error("zalo: cannot send, ZALO_BOT_TOKEN unset")
        return

    url = f"{ZALO_BASE}/bot{settings.zalo_bot_token}/sendMessage"
    chunks = _split(strip_markdown(text))

    async with httpx.AsyncClient(timeout=10.0) as client:
        for chunk in chunks:
            try:
                resp = await client.post(url, json={"chat_id": chat_id, "text": chunk})
                if resp.status_code >= 400:
                    log.error(
                        "zalo: sendMessage %s — %s", resp.status_code, resp.text[:500]
                    )
            except httpx.HTTPError as exc:
                log.exception("zalo: sendMessage failed: %s", exc)


async def set_webhook(url: str, secret_token: str) -> dict:
    """One-shot helper to register the webhook URL with Zalo. Used by
    scripts/setup_zalo_webhook.py — not called from request handlers."""
    settings = get_settings()
    if not settings.zalo_bot_token:
        raise RuntimeError("ZALO_BOT_TOKEN unset")
    api = f"{ZALO_BASE}/bot{settings.zalo_bot_token}/setWebhook"
    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.post(api, json={"url": url, "secret_token": secret_token})
        resp.raise_for_status()
        return resp.json()
