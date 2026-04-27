import hmac
from dataclasses import dataclass
from typing import Literal

from fastapi import Depends, Header, HTTPException, status
from firebase_admin import auth as fb_auth

from app.config import Settings, get_settings
from app.firestore import get_firebase_app

Role = Literal["owner", "manager"]
Actor = Literal["user", "agent"]


@dataclass(frozen=True, slots=True)
class Principal:
    """Who is making this request.

    actor="user"  → human via admin panel (Firebase ID token)
    actor="agent" → bot agent via API key (uid="openclaw")

    `primary_org_id` and `system_role` are populated for users when their
    Firebase token carries the matching custom claims; agent calls always
    use a singleton principal that doesn't carry org context (the org_id
    arrives as an explicit MCP tool argument instead).
    """

    actor: Actor
    uid: str
    role: Role
    email: str | None = None
    primary_org_id: str | None = None
    system_role: str | None = None  # e.g. "admin" — bypasses membership

    @property
    def audit_actor(self) -> str:
        return f"ai:{self.uid}" if self.actor == "agent" else f"user:{self.uid}"


def _verify_firebase_token(authorization: str | None) -> Principal:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "missing bearer token")
    token = authorization.split(" ", 1)[1]
    try:
        get_firebase_app()
        decoded = fb_auth.verify_id_token(token)
    except Exception as exc:  # noqa: BLE001 — firebase-admin raises many types
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "invalid token") from exc
    role: Role = decoded.get("role") or "manager"
    if role not in ("owner", "manager"):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "unrecognized role")
    return Principal(
        actor="user",
        uid=decoded["uid"],
        role=role,
        email=decoded.get("email"),
    )


def _verify_api_key(api_key: str | None, settings: Settings) -> Principal:
    if not api_key or not hmac.compare_digest(api_key, settings.openclaw_api_key):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "invalid api key")
    # Agent requests run with manager-equivalent role — no destructive bypass.
    return Principal(actor="agent", uid="openclaw", role="manager")


async def require_user(
    authorization: str | None = Header(default=None),
) -> Principal:
    """Admin-panel routes: Firebase ID token required."""
    return _verify_firebase_token(authorization)


async def require_owner(principal: Principal = Depends(require_user)) -> Principal:
    if principal.role != "owner":
        raise HTTPException(status.HTTP_403_FORBIDDEN, "owner role required")
    return principal


async def require_agent_or_user(
    authorization: str | None = Header(default=None),
    x_api_key: str | None = Header(default=None),
    settings: Settings = Depends(get_settings),
) -> Principal:
    """Accepts any of:
    - `X-API-Key: <api-key>`                       → agent (REST shim)
    - `Authorization: Bearer <api-key>`            → agent (MCP / Anthropic native)
    - `Authorization: Bearer <firebase-id-token>`  → user (admin panel)
    """
    if x_api_key:
        return _verify_api_key(x_api_key, settings)
    if authorization and authorization.lower().startswith("bearer "):
        token = authorization.split(" ", 1)[1]
        # Agent-key check first: constant-time compare avoids leaking key
        # contents via timing. A 64-char hex never looks like a JWT, so we
        # can short-circuit without touching firebase-admin.
        if hmac.compare_digest(token, settings.openclaw_api_key):
            return Principal(actor="agent", uid="openclaw", role="manager")
    return _verify_firebase_token(authorization)


async def require_org_id(
    x_org_id: str | None = Header(default=None),
    settings: Settings = Depends(get_settings),
) -> str:
    """Per-request org context. Frontend sends `X-Org-ID: <slug>`; if absent
    we fall back to `settings.default_org_id` (single-tenant convenience —
    fine until the second org goes live, at which point the frontend must
    start sending the header explicitly)."""
    return x_org_id or settings.default_org_id
