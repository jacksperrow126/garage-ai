"""HMAC-signed login tokens minted by the bot.

Flow:
  1. Brother chats Zalo: "đăng nhập web" / "cho tôi link login".
  2. Bot calls `get_login_url(zalo_id)` MCP tool → mints token here.
  3. Bot replies with `https://<admin>/login?token=<jwt>`.
  4. Brother taps link in Zalo → /login?token=... page POSTs token to
     `/public/auth/exchange` → backend verifies + mints a Firebase
     custom token → frontend calls `signInWithCustomToken`.

Domain separator vs `pdf_tokens.py`:
  Both modules sign with `openclaw_api_key`, but key derivation mixes in
  a domain string (b"login" here, b"pdf" there) — so a PDF token can
  never be replayed as a login token, even if a clever payload happened
  to deserialize the same way. This is a defense in depth and costs
  nothing.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time
from typing import Any

from app.config import get_settings

_DOMAIN = b"login"  # domain separator — see module docstring


def _key() -> bytes:
    return hmac.new(
        get_settings().openclaw_api_key.encode(), _DOMAIN, hashlib.sha256
    ).digest()


def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def _b64url_decode(s: str) -> bytes:
    return base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))


def mint_login_token(zalo_id: str, ttl_seconds: int = 600) -> tuple[str, int]:
    """Return (token, expires_at_unix). Default TTL is 10 minutes —
    long enough for the brother to tap the link, short enough that a
    leaked link expires before it's useful."""
    expires_at = int(time.time()) + ttl_seconds
    payload = json.dumps(
        {"z": zalo_id, "e": expires_at, "k": "login"},
        separators=(",", ":"),
        sort_keys=True,
    ).encode()
    sig = hmac.new(_key(), payload, hashlib.sha256).digest()
    return f"{_b64url(payload)}.{_b64url(sig)}", expires_at


def verify_login_token(token: str) -> dict[str, Any] | None:
    """Return {zalo_id} if the token is valid + unexpired, else None.
    Constant-time signature compare; broad except yields None on
    any malformed input."""
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
        # Reject anything that didn't come through mint_login_token.
        if data.get("k") != "login":
            return None
        if int(data["e"]) < int(time.time()):
            return None
        return {"zalo_id": str(data["z"])}
    except (json.JSONDecodeError, KeyError, TypeError, ValueError):
        return None
