"""Upload-token mint/verify roundtrip + cross-domain confusion checks."""

from __future__ import annotations

from app.services.auth_tokens import mint_login_token
from app.services.pdf_tokens import mint_invoice_pdf_token
from app.services.upload_tokens import mint_upload_token, verify_upload_token


def test_roundtrip_returns_zalo_id() -> None:
    token, _ = mint_upload_token("zalo-abc", ttl_seconds=600)
    assert verify_upload_token(token) == {"zalo_id": "zalo-abc"}


def test_expired_token_rejected() -> None:
    token, _ = mint_upload_token("zalo-abc", ttl_seconds=-10)
    assert verify_upload_token(token) is None


def test_login_token_cannot_be_used_for_upload() -> None:
    """Domain separator: login token shouldn't pass upload verification."""
    login_token, _ = mint_login_token("zalo-abc", ttl_seconds=600)
    assert verify_upload_token(login_token) is None


def test_pdf_token_cannot_be_used_for_upload() -> None:
    pdf_token, _ = mint_invoice_pdf_token("test-org", "INV-1", ttl_seconds=600)
    assert verify_upload_token(pdf_token) is None


def test_malformed_token_returns_none() -> None:
    assert verify_upload_token("") is None
    assert verify_upload_token("garbage") is None
    assert verify_upload_token("a.b") is None
