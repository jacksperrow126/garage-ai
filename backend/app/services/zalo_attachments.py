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


# Flat top-level string fields where Zalo Bot may put the image URL.
# Confirmed from prod webhook logs: `photo_url` for `message.image.received`
# events.
_FLAT_URL_FIELDS = ("photo_url", "image_url", "media_url", "thumb_url")


def extract_image_urls(message: dict[str, Any]) -> list[str]:
    """Return image URLs found anywhere in `message`.

    Tries known Zalo Bot envelope shapes (defensive — the API is sparsely
    documented and we've iterated this list as we see real events):
      - message.photo_url / image_url / media_url  (flat string)  ← Zalo Bot
      - message.attachments[] with type == image/photo/media
      - message.photo (single dict or list)
      - message.image (single dict)
    Order is preserved; duplicates are removed."""
    urls: list[str] = []

    # 1. Flat string URL fields — what Zalo Bot actually sends today.
    for field in _FLAT_URL_FIELDS:
        v = message.get(field)
        if isinstance(v, str) and v.startswith(("http://", "https://")):
            urls.append(v)

    # 2. attachments[] — Telegram-ish shape, kept defensive.
    for attachment in message.get("attachments") or []:
        if not isinstance(attachment, dict):
            continue
        atype = str(attachment.get("type", "")).lower()
        if atype in ("image", "photo", "media"):
            url = _find_url(attachment)
            if url:
                urls.append(url)

    # 3. nested photo dict / list of size variants.
    photo = message.get("photo")
    if isinstance(photo, dict):
        if (u := _find_url(photo)):
            urls.append(u)
    elif isinstance(photo, list):
        for entry in photo:
            if isinstance(entry, dict) and (u := _find_url(entry)):
                urls.append(u)

    # 4. nested image dict.
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


def _sniff_mime(data: bytes) -> str:
    """Detect image MIME from magic bytes — never trust upstream
    Content-Type. Anthropic only accepts these four MIME values, so
    we constrain our return to that set; unknown types default to
    image/jpeg (most common case from Zalo CDN)."""
    if data[:3] == b"\xff\xd8\xff":
        return "image/jpeg"
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return "image/png"
    if data[:6] in (b"GIF87a", b"GIF89a"):
        return "image/gif"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    log.warning("unknown image magic bytes %r — defaulting to image/jpeg", data[:8])
    return "image/jpeg"


async def download_image(url: str) -> ImageInput:
    """Fetch an image URL into memory.

    Zalo CDN (zdn.vn) serves images as public objects but some hosts /
    paths reject the default httpx User-Agent and need a browser-shaped
    one. We try in order: plain GET with browser UA → plain GET without
    UA → Bearer-token auth (in case Zalo ever locks down). Raises
    RuntimeError with diagnostic detail if all attempts fail.

    MIME is sniffed from magic bytes, not the upstream Content-Type —
    Zalo returns variants like 'image/jpg' that Anthropic's strict
    validator rejects."""
    settings = get_settings()
    bot_token = settings.zalo_bot_token

    # Browser-shaped UA — Zalo CDN sometimes 403s default httpx UA.
    browser_ua = (
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    )
    attempts: list[tuple[str, dict[str, str]]] = [
        ("browser-ua", {"User-Agent": browser_ua}),
        ("plain", {}),
    ]
    if bot_token:
        attempts.append(
            ("bearer-token", {"Authorization": f"Bearer {bot_token}"})
        )

    diagnostics: list[str] = []
    async with httpx.AsyncClient(timeout=20.0, follow_redirects=True) as client:
        for label, headers in attempts:
            try:
                resp = await client.get(url, headers=headers)
            except Exception as exc:  # noqa: BLE001 — log everything
                diagnostics.append(f"{label}: {type(exc).__name__}: {exc!r}")
                log.warning(
                    "zalo image download failed (%s): %s: %r",
                    label,
                    type(exc).__name__,
                    exc,
                )
                continue
            if resp.status_code == 200 and resp.content:
                log.info(
                    "zalo image download ok via %s (%d bytes)",
                    label,
                    len(resp.content),
                )
                return ImageInput(data=resp.content, mime=_sniff_mime(resp.content))
            diagnostics.append(
                f"{label}: HTTP {resp.status_code} ({len(resp.content)} bytes)"
            )

    raise RuntimeError(
        f"image download failed for {url} — attempts: {'; '.join(diagnostics)}"
    )
