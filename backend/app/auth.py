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
        # Custom claims set in /public/auth/exchange — drive multi-tenant
        # authorization. Absent for users who never logged in via the bot
        # path (e.g. anonymous dev sign-ins) — those fall through to
        # default_org_id with no membership, so they only see whatever
        # org default_org_id points at.
        primary_org_id=decoded.get("primary_org_id"),
        system_role=decoded.get("system_role"),
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
    principal: Principal = Depends(require_agent_or_user),
) -> str:
    """Per-request org context + membership enforcement.

    Frontend sends `X-Org-ID: <slug>`; if absent we fall back to
    `settings.default_org_id`. For *user* principals we then verify
    they're allowed to access that org — using the `primary_org_id` /
    `system_role` custom claims that the Zalo login exchange stamps on
    the Firebase user.

    Trust model:
      - User: must have primary_org_id == requested org_id, OR
              system_role == "admin" (cross-org bypass).
      - Agent: trusted (the agent's MCP prompt threads the right org_id
              through tool args; see mcp_server.py module docstring).

    A user with no primary_org_id claim (e.g. anonymous dev sign-in)
    can still hit endpoints scoped to default_org_id, but any other
    org_id is rejected. This keeps local dev usable while enforcing
    the production isolation guarantee.
    """
    org_id = x_org_id or settings.default_org_id
    if principal.actor == "user" and principal.system_role != "admin":
        # No primary_org_id → only default_org_id is accessible.
        # Different primary_org_id → 403.
        if principal.primary_org_id is None:
            if org_id != settings.default_org_id:
                raise HTTPException(
                    status.HTTP_403_FORBIDDEN,
                    "no org membership; cannot access requested org",
                )
        elif principal.primary_org_id != org_id:
            raise HTTPException(
                status.HTTP_403_FORBIDDEN,
                f"not a member of org {org_id}",
            )
    return org_id
