"""HMAC-signed tokens for unauthenticated PDF download URLs.

The bot mints these via the `get_invoice_pdf_url` MCP tool and sends the
URL to the user over Zalo. Whoever has the link can download the PDF
until it expires — that's the point. Treat them like password-reset
links: short TTL, single purpose, no extra capability beyond reading
ONE invoice's PDF.

Format (JWS-compact-ish, no header — we have one algorithm):
    base64url(payload_json) "." base64url(hmac_sha256(payload))

The signing key reuses `openclaw_api_key` since rotating that already
invalidates everything the agent can do. Adding a separate signing key
would just be one more secret to manage.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time
from typing import Any

from app.config import get_settings


def _key() -> bytes:
    return get_settings().openclaw_api_key.encode()


def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def _b64url_decode(s: str) -> bytes:
    return base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))


def mint_invoice_pdf_token(
    org_id: str, invoice_id: str, ttl_seconds: int = 86_400
) -> tuple[str, int]:
    """Return (token, expires_at_unix). Default TTL is 24h."""
    expires_at = int(time.time()) + ttl_seconds
    payload = json.dumps(
        {"o": org_id, "i": invoice_id, "e": expires_at},
        separators=(",", ":"),
        sort_keys=True,
    ).encode()
    sig = hmac.new(_key(), payload, hashlib.sha256).digest()
    return f"{_b64url(payload)}.{_b64url(sig)}", expires_at


def verify_invoice_pdf_token(token: str) -> dict[str, Any] | None:
    """Return {org_id, invoice_id} if the token is valid + unexpired,
    else None. Constant-time signature compare; broad except is
    intentional — any malformed input yields None, never an exception."""
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
        if int(data["e"]) < int(time.time()):
            return None
        return {"org_id": str(data["o"]), "invoice_id": str(data["i"])}
    except (json.JSONDecodeError, KeyError, TypeError, ValueError):
        return None
