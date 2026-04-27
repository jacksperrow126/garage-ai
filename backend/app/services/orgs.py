"""Organization (tenant) CRUD and membership.

Each organization owns its own subtree of products/invoices/etc — see
docs/MULTI_TENANT.md for the full layout. This module is the source of
truth for org existence and membership; all service-layer reads/writes
that scope to an org should validate via `get_org()` / `is_member()` first.

Slug rules:
  * lowercased
  * Vietnamese diacritics stripped (the same `unidecode`-style approach
    we already use for SKUs in inventory.py)
  * spaces → "-"
  * non-alphanumeric stripped
  * appended numeric suffix on collision ("-2", "-3", ...)
"""

from __future__ import annotations

import re
import unicodedata
from typing import Any

from app.firestore import get_db, server_timestamp


def slugify(name: str) -> str:
    # `Đ`/`đ` (Latin D with stroke, U+0110/U+0111) are precomposed and
    # don't decompose under NFD/NFKD — substitute manually first or
    # they get silently dropped on ASCII-encode. Other Vietnamese
    # diacritics (ă, ấ, ầ, …) decompose cleanly.
    substituted = name.replace("Đ", "D").replace("đ", "d")
    decomposed = unicodedata.normalize("NFKD", substituted)
    ascii_only = decomposed.encode("ascii", "ignore").decode("ascii")
    lowered = ascii_only.lower()
    cleaned = re.sub(r"[^a-z0-9]+", "-", lowered).strip("-")
    return cleaned or "garage"


def _unique_slug(base: str) -> str:
    db = get_db()
    candidate = base
    i = 2
    while db.collection("organizations").document(candidate).get().exists:
        candidate = f"{base}-{i}"
        i += 1
    return candidate


def create_org(name: str, owner_zalo_id: str) -> dict[str, Any]:
    """Create a new org. Slug derived from name; suffix on collision."""
    org_id = _unique_slug(slugify(name))
    data = {
        "name": name,
        "slug": org_id,
        "owner_zalo_id": owner_zalo_id,
        "active": True,
        "created_at": server_timestamp(),
    }
    get_db().collection("organizations").document(org_id).set(data)
    # The creator is the first owner-member.
    add_member(org_id, owner_zalo_id, role="owner", added_by=owner_zalo_id)
    return {"id": org_id, **{k: v for k, v in data.items() if k != "created_at"}}


def get_org(org_id: str) -> dict[str, Any] | None:
    snap = get_db().collection("organizations").document(org_id).get()
    if not snap.exists:
        return None
    return {"id": snap.id, **(snap.to_dict() or {})}


def list_orgs() -> list[dict[str, Any]]:
    return [
        {"id": s.id, **(s.to_dict() or {})}
        for s in get_db().collection("organizations").stream()
    ]


def add_member(
    org_id: str, zalo_id: str, role: str, added_by: str
) -> None:
    """Add a Zalo user as a member of an org. Idempotent — re-adding
    overwrites the role (useful for promotion/demotion)."""
    get_db().collection("organizations").document(org_id).collection("members").document(
        zalo_id
    ).set(
        {
            "role": role,
            "added_at": server_timestamp(),
            "added_by": added_by,
        }
    )


def is_member(org_id: str, zalo_id: str) -> bool:
    return (
        get_db()
        .collection("organizations")
        .document(org_id)
        .collection("members")
        .document(zalo_id)
        .get()
        .exists
    )


def member_role(org_id: str, zalo_id: str) -> str | None:
    snap = (
        get_db()
        .collection("organizations")
        .document(org_id)
        .collection("members")
        .document(zalo_id)
        .get()
    )
    if not snap.exists:
        return None
    return (snap.to_dict() or {}).get("role")
