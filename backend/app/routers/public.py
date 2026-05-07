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

from fastapi import APIRouter, File, Form, HTTPException, Query, Response, UploadFile, status
from firebase_admin import auth as fb_auth
from pydantic import BaseModel

from app.firestore import get_firebase_app
from app.services import (
    agent,
    conversation,
    invoice_pdf,
    invoice_read,
    orgs as orgs_service,
    zalo_client,
    zalo_users,
)
from app.services.auth_tokens import verify_login_token
from app.services.pdf_tokens import verify_invoice_pdf_token
from app.services.upload_tokens import verify_upload_token
from app.services.zalo_attachments import ImageInput, detect_image_mime

log = logging.getLogger(__name__)

router = APIRouter(prefix="/public", tags=["public"])

MAX_UPLOAD_BYTES = 10 * 1024 * 1024  # 10 MB
ALLOWED_IMAGE_MIMES = frozenset({"image/jpeg", "image/png", "image/gif", "image/webp"})


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
        # Log token prefix (not the full token — it's still valid until
        # expiry, even if the verify call failed for non-expiry reasons).
        # 8 chars is enough to correlate against the bot's mint event in
        # audit logs without giving away the signature.
        log.info("login.exchange: rejected token prefix=%r", body.token[:8])
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
    persistent_claims: dict = {
        "role": role,
        "primary_org_id": primary_org_id,
        "zalo_name": name,
    }
    # system_role flag drives the cross-org bypass in `require_org_id`.
    # Only set when the zalo_users record explicitly has it — we never
    # invent admin status here.
    if is_admin:
        persistent_claims["system_role"] = "admin"

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


# ── Direct file upload (Zalo CDN bypass) ────────────────────────────────


class _UploadAnalyzeResponse(BaseModel):
    reply_text: str
    sent_to_zalo: bool


@router.post("/uploads/analyze", response_model=_UploadAnalyzeResponse)
async def upload_and_analyze(
    t: str = Query(..., description="HMAC token from get_upload_url"),
    file: UploadFile = File(...),
    caption: str = Form(default=""),
) -> _UploadAnalyzeResponse:
    """User uploads an image / PDF / text file via the web bypass form;
    we run it through the same agent flow as a Zalo chat turn (same
    history, same MCP tools), reply to the user's Zalo chat for
    continuity, and return the reply to the web page so the user sees
    immediate confirmation.

    Bytes are processed in memory and discarded — we never write the
    upload to disk or Firebase Storage."""
    claims = verify_upload_token(t)
    if not claims:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "invalid or expired link")
    zalo_id = claims["zalo_id"]

    user = zalo_users.get(zalo_id)
    if not user or not user.get("primary_org_id"):
        raise HTTPException(
            status.HTTP_403_FORBIDDEN, "user has no primary org — request access first"
        )

    raw = await file.read()
    if len(raw) > MAX_UPLOAD_BYTES:
        raise HTTPException(
            status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            f"file too large ({len(raw)} > {MAX_UPLOAD_BYTES} bytes)",
        )
    if not raw:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "empty file")

    # Detect kind from magic bytes — never trust client-supplied
    # Content-Type. Three branches: image, PDF, text fallback.
    image: ImageInput | None = None
    pdf_bytes: bytes | None = None
    extra_text = ""

    image_mime = detect_image_mime(raw)
    if image_mime:
        image = ImageInput(data=raw, mime=image_mime)
    elif raw[:5] == b"%PDF-":
        pdf_bytes = raw
    else:
        # Treat as text. Decode best-effort; reject if it doesn't look
        # text-y (high ratio of non-printable bytes = binary garbage).
        try:
            decoded = raw.decode("utf-8")
        except UnicodeDecodeError:
            try:
                decoded = raw.decode("latin-1")
            except UnicodeDecodeError:
                raise HTTPException(
                    status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
                    "file is not an image, PDF, or readable text",
                ) from None
        # Cheap binary-ish check: lots of NUL bytes → binary.
        if decoded.count("\x00") > len(decoded) * 0.01:
            raise HTTPException(
                status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
                "file appears binary; only image/PDF/text supported",
            )
        # Cap embedded text so a huge .csv doesn't blow up the prompt.
        if len(decoded) > 50_000:
            decoded = decoded[:50_000] + "\n…(file đã cắt do quá dài)"
        extra_text = f"\n\n--- Nội dung file {file.filename or 'tệp'} ---\n{decoded}"

    org_id = user["primary_org_id"]
    user_role = user.get("system_role") or "member"
    display = user.get("name")
    onboarding_step = user.get("onboarding_step")

    composed_text = (caption or "").strip() + extra_text
    history = conversation.load(zalo_id)

    try:
        reply_text, assistant_content = await agent.reply(
            composed_text or "(người dùng upload tệp qua web)",
            org_id=org_id,
            user_role=user_role,
            user_display_name=display,
            history=history,
            zalo_id=zalo_id,
            image=image,
            pdf_bytes=pdf_bytes,
            onboarding_step=onboarding_step,
        )
    except Exception as exc:
        log.exception("upload analyze: agent.reply failed: %s", exc)
        raise HTTPException(
            status.HTTP_502_BAD_GATEWAY, "không phân tích được tệp, anh thử lại sau"
        ) from exc

    # Persist a placeholder turn so chat history reflects the upload.
    persisted_text = (
        f"[upload {file.filename or 'tệp'}] {caption}".strip()
    )
    try:
        conversation.append_turn(zalo_id, persisted_text, assistant_content)
    except Exception as exc:
        log.exception("upload analyze: conversation persist failed: %s", exc)

    # Mirror the reply into the user's Zalo chat for continuity.
    sent_to_zalo = False
    try:
        await zalo_client.send_message(zalo_id, reply_text)
        sent_to_zalo = True
    except Exception as exc:
        log.exception("upload analyze: zalo send failed: %s", exc)

    return _UploadAnalyzeResponse(reply_text=reply_text, sent_to_zalo=sent_to_zalo)
