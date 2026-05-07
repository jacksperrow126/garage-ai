"""Unauthenticated, token-protected endpoints — invoice PDFs and the
Zalo-bot-mediated login flow.

Two surfaces today:
  - GET /public/invoices/{id}/pdf?t=<pdf-token>  — see pdf_tokens.py
  - POST /public/auth/exchange                   — see auth_tokens.py

Both verify HMAC tokens minted by the bot via MCP tools. The tokens use
domain separation so a PDF token can never be replayed as a login token.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException, Query, Response, status
from firebase_admin import auth as fb_auth
from pydantic import BaseModel

from app.firestore import get_firebase_app
from app.services import invoice_pdf, invoice_read, orgs as orgs_service, zalo_users
from app.services.auth_tokens import verify_login_token
from app.services.pdf_tokens import verify_invoice_pdf_token

log = logging.getLogger(__name__)

router = APIRouter(prefix="/public", tags=["public"])


@router.get("/invoices/{invoice_id}/pdf")
def public_invoice_pdf(
    invoice_id: str,
    t: str = Query(..., description="HMAC token minted by get_invoice_pdf_url"),
) -> Response:
    claims = verify_invoice_pdf_token(t)
    if not claims:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "invalid or expired link")
    if claims["invoice_id"] != invoice_id:
        # Token is signed by us but for a different invoice — refuse.
        # Belt-and-suspenders: prevents a leaked token from being remixed
        # to fetch a sibling invoice in the same org.
        raise HTTPException(status.HTTP_403_FORBIDDEN, "token / invoice mismatch")

    org_id = claims["org_id"]
    inv = invoice_read.get_invoice(org_id, invoice_id)
    if not inv:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "invoice not found")
    org = orgs_service.get_org(org_id)
    if not org:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "org not found")

    pdf_bytes = invoice_pdf.render_invoice_pdf(org, inv)
    filename = f"hoa-don-{invoice_id}.pdf"
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={
            # `inline` lets mobile browsers preview the PDF in-place; users
            # can then Share → Zalo from the preview. `attachment` would
            # force a download which is awkward inside Zalo's webview.
            "Content-Disposition": f'inline; filename="{filename}"',
            # Don't let intermediaries cache a tokenized URL.
            "Cache-Control": "private, no-store",
        },
    )


# ── Zalo-mediated login ─────────────────────────────────────────────────


class _LoginExchangeRequest(BaseModel):
    token: str


class _LoginExchangeResponse(BaseModel):
    custom_token: str
    uid: str
    name: str
    primary_org_id: str | None
    role: str


@router.post("/auth/exchange", response_model=_LoginExchangeResponse)
def exchange_login_token(body: _LoginExchangeRequest) -> _LoginExchangeResponse:
    """Exchange a one-time HMAC login token for a Firebase custom token.

    The bot mints the HMAC token via `get_login_url`, sends the URL to
    the user's Zalo chat. When the user taps the link, the frontend
    POSTs the token here; we verify it, persist the user's role +
    org as Firebase custom claims (so they survive ID-token refresh),
    and return a Firebase custom token for `signInWithCustomToken`.
    """
    claims = verify_login_token(body.token)
    if not claims:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "invalid or expired link")

    zalo_id = claims["zalo_id"]
    user = zalo_users.get(zalo_id)
    if not user:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "zalo user not found")

    # Map zalo_users → Firebase custom claims. system_role=admin is the
    # global admin (cross-org). Otherwise use 'owner' since the user has
    # a primary_org_id assigned (i.e. they were approved into an org).
    primary_org_id = user.get("primary_org_id")
    is_admin = user.get("system_role") == "admin"
    role = "owner" if (is_admin or primary_org_id) else "manager"

    name = user.get("name") or "User"
    persistent_claims = {
        "role": role,
        "primary_org_id": primary_org_id,
        "zalo_name": name,
    }

    get_firebase_app()  # ensure firebase-admin is initialized

    # Persist claims so they survive ID-token refresh (Firebase auto-
    # refreshes hourly). Auto-create the auth user on first login.
    try:
        fb_auth.set_custom_user_claims(zalo_id, persistent_claims)
    except fb_auth.UserNotFoundError:
        fb_auth.create_user(uid=zalo_id, display_name=name)
        fb_auth.set_custom_user_claims(zalo_id, persistent_claims)

    custom_token = fb_auth.create_custom_token(
        zalo_id, developer_claims=persistent_claims
    )
    log.info("login.exchange: minted custom token for zalo_id=%s role=%s", zalo_id, role)
    return _LoginExchangeResponse(
        custom_token=custom_token.decode("utf-8"),
        uid=zalo_id,
        name=name,
        primary_org_id=primary_org_id,
        role=role,
    )
