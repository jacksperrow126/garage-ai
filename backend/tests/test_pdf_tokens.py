"""Token mint/verify roundtrip + tampering / expiry handling."""

from __future__ import annotations

import json
import time

from app.services.pdf_tokens import (
    _b64url,
    _b64url_decode,
    mint_invoice_pdf_token,
    verify_invoice_pdf_token,
)


def test_roundtrip_returns_claims() -> None:
    token, expires_at = mint_invoice_pdf_token("test-org", "INV-1", ttl_seconds=120)
    claims = verify_invoice_pdf_token(token)
    assert claims == {"org_id": "test-org", "invoice_id": "INV-1"}
    assert expires_at > int(time.time())


def test_expired_token_rejected() -> None:
    # Mint with negative TTL → already expired.
    token, _ = mint_invoice_pdf_token("test-org", "INV-1", ttl_seconds=-10)
    assert verify_invoice_pdf_token(token) is None


def test_tampered_payload_rejected() -> None:
    """Flipping one byte in the payload breaks the HMAC. We simulate the
    flip by re-encoding a payload with a different invoice_id but keeping
    the original signature."""
    token, _ = mint_invoice_pdf_token("test-org", "INV-1", ttl_seconds=120)
    payload_b64, sig_b64 = token.split(".", 1)
    payload = json.loads(_b64url_decode(payload_b64))
    payload["i"] = "INV-2-attacker"
    forged = (
        _b64url(json.dumps(payload, separators=(",", ":"), sort_keys=True).encode())
        + "."
        + sig_b64
    )
    assert verify_invoice_pdf_token(forged) is None


def test_malformed_token_returns_none() -> None:
    assert verify_invoice_pdf_token("") is None
    assert verify_invoice_pdf_token("not-a-token") is None
    assert verify_invoice_pdf_token("a.b.c") is None
    assert verify_invoice_pdf_token("a.notbase64!@#") is None
