"""Best-effort extraction + download of image attachments from Zalo
webhook messages.

The Zalo Bot API webhook envelope for non-text events isn't well-
documented; we search a list of known field shapes and dedupe URLs.
Callers should log raw bodies for any image event we fail to extract
from, so we can extend the path list."""

from __future__ import annotations

import base64
import logging
from dataclasses import dataclass
from typing import Any

import httpx

from app.config import get_settings

log = logging.getLogger(__name__)

# Field names that *might* hold the image URL inside an attachment dict.
# Searched in order; first http(s) match wins.
_URL_FIELD_HINTS = ("url", "href", "image_url", "media_url", "src", "thumbnail")


@dataclass(frozen=True, slots=True)
class ImageInput:
    """An image ready to forward to Anthropic. `mime` is the IANA media
    type as reported by the source (defaults to image/jpeg if unknown)."""

    data: bytes
    mime: str = "image/jpeg"

    @property
    def b64(self) -> str:
        return base64.b64encode(self.data).decode()


def extract_image_urls(message: dict[str, Any]) -> list[str]:
    """Return image URLs found anywhere in `message`.

    Tries common Zalo Bot envelope shapes:
      - message.attachments[] with type == image/photo/media
      - message.photo (single dict or list)
      - message.image (single dict)
    Order is preserved; duplicates are removed."""
    urls: list[str] = []

    for attachment in message.get("attachments") or []:
        if not isinstance(attachment, dict):
            continue
        atype = str(attachment.get("type", "")).lower()
        if atype in ("image", "photo", "media"):
            url = _find_url(attachment)
            if url:
                urls.append(url)

    photo = message.get("photo")
    if isinstance(photo, dict):
        if (u := _find_url(photo)):
            urls.append(u)
    elif isinstance(photo, list):
        for entry in photo:
            if isinstance(entry, dict) and (u := _find_url(entry)):
                urls.append(u)

    image = message.get("image")
    if isinstance(image, dict):
        if (u := _find_url(image)):
            urls.append(u)

    seen: set[str] = set()
    deduped: list[str] = []
    for u in urls:
        if u not in seen:
            seen.add(u)
            deduped.append(u)
    return deduped


def _find_url(d: dict[str, Any]) -> str | None:
    for hint in _URL_FIELD_HINTS:
        v = d.get(hint)
        if isinstance(v, str) and v.startswith(("http://", "https://")):
            return v
    return None


async def download_image(url: str) -> ImageInput:
    """Fetch an image URL into memory.

    Tries Bearer auth with the bot token first (Zalo CDN sometimes
    requires it for fresh-uploaded media), falls back to plain GET.
    Raises RuntimeError if both attempts fail."""
    settings = get_settings()
    auth_attempt = (
        {"Authorization": f"Bearer {settings.zalo_bot_token}"}
        if settings.zalo_bot_token
        else None
    )
    last_status: int | None = None
    async with httpx.AsyncClient(timeout=15.0, follow_redirects=True) as client:
        for headers in (auth_attempt, {}):
            if headers is None:
                continue
            try:
                resp = await client.get(url, headers=headers)
            except httpx.HTTPError as exc:
                log.warning("zalo image download error: %s", exc)
                continue
            last_status = resp.status_code
            if resp.status_code == 200 and resp.content:
                mime = resp.headers.get("content-type", "image/jpeg").split(";")[0].strip()
                return ImageInput(data=resp.content, mime=mime)
    raise RuntimeError(f"image download failed (last status={last_status}): {url}")
