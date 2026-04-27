"""Zalo user identity layer.

`zalo_users/{zalo_id}` is the bot-side counterpart to Firebase `users/`.
A Zalo user is the entity authorized by the Zalo platform's `from.id`;
multiple Zalo users may belong to the same human (rare) but for our
purposes one Zalo id = one identity.

Fields:
  name (str)              : display_name from Zalo
  system_role             : "admin" | None — admin bypasses org membership
  primary_org_id          : default org for tool-call scoping
  added_at, added_by      : audit trail
"""

from __future__ import annotations

from typing import Any

from app.firestore import get_db, server_timestamp


def get(zalo_id: str) -> dict[str, Any] | None:
    snap = get_db().collection("zalo_users").document(zalo_id).get()
    if not snap.exists:
        return None
    return {"id": snap.id, **(snap.to_dict() or {})}


def is_admin(zalo_id: str) -> bool:
    user = get(zalo_id)
    return bool(user and user.get("system_role") == "admin")


def upsert(
    zalo_id: str,
    name: str,
    *,
    system_role: str | None = None,
    primary_org_id: str | None = None,
    added_by: str | None = None,
) -> None:
    """Idempotent create-or-update. None-valued fields are not written
    (so a later upsert without `system_role` doesn't strip admin)."""
    payload: dict[str, Any] = {
        "name": name,
        "updated_at": server_timestamp(),
    }
    if system_role is not None:
        payload["system_role"] = system_role
    if primary_org_id is not None:
        payload["primary_org_id"] = primary_org_id
    if added_by is not None:
        payload["added_by"] = added_by

    ref = get_db().collection("zalo_users").document(zalo_id)
    if ref.get().exists:
        ref.update(payload)
    else:
        ref.set({**payload, "added_at": server_timestamp()})


def set_primary_org(zalo_id: str, org_id: str) -> None:
    get_db().collection("zalo_users").document(zalo_id).update(
        {"primary_org_id": org_id, "updated_at": server_timestamp()}
    )
