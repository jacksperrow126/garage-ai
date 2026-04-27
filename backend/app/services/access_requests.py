"""Bot-mediated org-access onboarding.

Flow:
  1. Unknown Zalo user sends the bot a message.
  2. Webhook (`routers/zalo.py`) calls `create_or_get_pending()` to either
     surface their existing pending request or create a fresh one, then
     DMs every admin on Zalo.
  3. The admin replies in their own bot conversation. Claude (via the
     agent's system prompt) recognizes the approval/denial intent and
     calls `approve_access_request` or `deny_access_request` MCP tools.
  4. Approval creates an `organizations/{org}/members/{requester}` doc
     and sets the requester's `zalo_users.primary_org_id`. Denial just
     marks the request and notifies the requester.

Stored at the *global* (non-org-scoped) collection `access_requests/`
because the request itself doesn't belong to any org until approved.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any

from app.firestore import get_db, server_timestamp
from app.services import orgs, zalo_users

log = logging.getLogger(__name__)


def list_admins() -> list[dict[str, Any]]:
    """Return all zalo_users with system_role=admin. Used to fan out DMs
    when a new request comes in."""
    return [
        {"id": s.id, **(s.to_dict() or {})}
        for s in get_db()
        .collection("zalo_users")
        .where("system_role", "==", "admin")
        .stream()
    ]


def find_pending_for(zalo_id: str) -> dict[str, Any] | None:
    db = get_db()
    snaps = list(
        db.collection("access_requests")
        .where("zalo_id", "==", zalo_id)
        .where("status", "==", "pending")
        .limit(1)
        .stream()
    )
    if not snaps:
        return None
    snap = snaps[0]
    return {"id": snap.id, **(snap.to_dict() or {})}


def create_or_get_pending(
    zalo_id: str, display_name: str | None, message: str
) -> tuple[dict[str, Any], bool]:
    """Return (request, is_new). If the user already has a pending request,
    we don't create a duplicate — they already have one in the queue."""
    existing = find_pending_for(zalo_id)
    if existing:
        return existing, False

    ref = get_db().collection("access_requests").document()
    payload = {
        "zalo_id": zalo_id,
        "display_name": display_name,
        "message": message,
        "status": "pending",
        "created_at": server_timestamp(),
        "resolved_at": None,
        "resolved_by": None,
        "org_id": None,
        "role": None,
    }
    ref.set(payload)
    payload["id"] = ref.id
    return payload, True


def list_pending() -> list[dict[str, Any]]:
    return [
        {"id": s.id, **(s.to_dict() or {})}
        for s in get_db()
        .collection("access_requests")
        .where("status", "==", "pending")
        .stream()
    ]


def approve(
    request_id: str,
    target_org_id: str,
    role: str,
    resolved_by_zalo_id: str,
) -> dict[str, Any]:
    """Mark a pending request approved, create the org membership, and
    set the requester's primary_org_id. Idempotency is best-effort: if
    called twice on the same request_id we 400 on the second call."""
    db = get_db()
    ref = db.collection("access_requests").document(request_id)
    snap = ref.get()
    if not snap.exists:
        raise ValueError(f"access request {request_id} not found")
    data = snap.to_dict() or {}
    if data.get("status") != "pending":
        raise ValueError(
            f"access request {request_id} is {data.get('status')}, not pending"
        )
    if not orgs.get_org(target_org_id):
        raise ValueError(f"org {target_org_id} does not exist")

    requester_zalo_id = data["zalo_id"]
    requester_name = data.get("display_name") or "Unknown"

    # Add the user record (or update if they had a stub already).
    zalo_users.upsert(
        requester_zalo_id,
        name=requester_name,
        primary_org_id=target_org_id,
        added_by=resolved_by_zalo_id,
    )
    orgs.add_member(target_org_id, requester_zalo_id, role=role, added_by=resolved_by_zalo_id)

    ref.update(
        {
            "status": "approved",
            "resolved_at": server_timestamp(),
            "resolved_by": resolved_by_zalo_id,
            "org_id": target_org_id,
            "role": role,
        }
    )
    return {
        "id": request_id,
        "zalo_id": requester_zalo_id,
        "org_id": target_org_id,
        "role": role,
        "resolved_at": datetime.now(UTC),
    }


def deny(
    request_id: str, reason: str, resolved_by_zalo_id: str
) -> dict[str, Any]:
    db = get_db()
    ref = db.collection("access_requests").document(request_id)
    snap = ref.get()
    if not snap.exists:
        raise ValueError(f"access request {request_id} not found")
    data = snap.to_dict() or {}
    if data.get("status") != "pending":
        raise ValueError(
            f"access request {request_id} is {data.get('status')}, not pending"
        )
    ref.update(
        {
            "status": "denied",
            "resolved_at": server_timestamp(),
            "resolved_by": resolved_by_zalo_id,
            "deny_reason": reason or None,
        }
    )
    return {
        "id": request_id,
        "zalo_id": data["zalo_id"],
        "reason": reason,
        "resolved_at": datetime.now(UTC),
    }
