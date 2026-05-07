"""HMAC-signed tokens for the web upload bypass.

Brother chats Zalo with a photo → CDN blocks Cloud Run download → bot
mints an upload URL via `get_upload_url` MCP tool → user opens link in
browser → uploads bytes directly → backend processes via agent + sends
reply back to Zalo chat AND returns it to the upload page.

Domain separator vs `auth_tokens.py` / `pdf_tokens.py`: same signing
key, mixed with b"upload" — a token from any other domain can't be
replayed here, even if payload shapes happened to align.

TTL default 30 minutes — same as login link, for similar reasons.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time
from typing import Any

from app.config import get_settings

_DOMAIN = b"upload"


def _key() -> bytes:
    return hmac.new(
        get_settings().openclaw_api_key.encode(), _DOMAIN, hashlib.sha256
    ).digest()


def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def _b64url_decode(s: str) -> bytes:
    return base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))


def mint_upload_token(zalo_id: str, ttl_seconds: int = 1800) -> tuple[str, int]:
    """Return (token, expires_at_unix). Default TTL 30 min."""
    expires_at = int(time.time()) + ttl_seconds
    payload = json.dumps(
        {"z": zalo_id, "e": expires_at, "k": "upload"},
        separators=(",", ":"),
        sort_keys=True,
    ).encode()
    sig = hmac.new(_key(), payload, hashlib.sha256).digest()
    return f"{_b64url(payload)}.{_b64url(sig)}", expires_at


def verify_upload_token(token: str) -> dict[str, Any] | None:
    """Return {zalo_id} if valid + unexpired, else None."""
    try:
        payload_b64, sig_b64 = token.split(".", 1)
        payload = _b64url_decode(payload_b64)
        sig = _b64url_decode(sig_b64)
    except (ValueError, base64.binascii.Error):
        return None
    expected_sig = hmac.new(_key(), payload, hashlib.sha256).digest()
    if not hmac.compare_digest(sig, expected_sig):
        return None
    try:
        data = json.loads(payload)
        if data.get("k") != "upload":
            return None
        if int(data["e"]) < int(time.time()):
            return None
        return {"zalo_id": str(data["z"])}
    except (json.JSONDecodeError, KeyError, TypeError, ValueError):
        return None
