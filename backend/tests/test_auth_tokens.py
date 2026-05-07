"""Login-token mint/verify roundtrip + domain-separation against PDF tokens."""

from __future__ import annotations

import time

from app.services.auth_tokens import mint_login_token, verify_login_token
from app.services.pdf_tokens import mint_invoice_pdf_token


def test_roundtrip_returns_zalo_id() -> None:
    token, expires_at = mint_login_token("zalo-abc-123", ttl_seconds=600)
    claims = verify_login_token(token)
    assert claims == {"zalo_id": "zalo-abc-123"}
    assert expires_at > int(time.time())


def test_expired_login_token_rejected() -> None:
    token, _ = mint_login_token("zalo-abc-123", ttl_seconds=-10)
    assert verify_login_token(token) is None


def test_pdf_token_cannot_be_used_for_login() -> None:
    """Domain separator on the HMAC key derivation must prevent a valid
    PDF token from passing login verification, even if the payload
    happened to contain a zalo_id-shaped field."""
    pdf_token, _ = mint_invoice_pdf_token("test-org", "INV-1", ttl_seconds=600)
    assert verify_login_token(pdf_token) is None


def test_login_token_cannot_be_used_for_pdf() -> None:
    """Other direction of the same defense — login tokens shouldn't
    open PDFs even if you tried."""
    from app.services.pdf_tokens import verify_invoice_pdf_token

    login_token, _ = mint_login_token("zalo-abc-123", ttl_seconds=600)
    assert verify_invoice_pdf_token(login_token) is None


def test_malformed_login_token_returns_none() -> None:
    assert verify_login_token("") is None
    assert verify_login_token("not.a.token") is None
    assert verify_login_token("a.b") is None
