"""Two-phase confirmation for destructive MCP tools.

Flow:
  1. Agent calls e.g. `create_import_invoice(...)` → we validate the input,
     stash it under a UUID, and return `{preview_id, summary}` WITHOUT writing.
  2. Agent shows the summary to the user in Zalo ("you're about to import
     5 × OIL5W30 @ 180k = 900k, ok?").
  3. Agent calls `confirm_action(preview_id)` and we commit.

Previews are stored at `organizations/{org_id}/previews/{preview_id}` so each
org has its own preview namespace and one org can't consume another's preview.
"""

from __future__ import annotations

import secrets
from datetime import UTC, datetime, timedelta
from typing import Any, Literal

from fastapi import HTTPException, status
from google.cloud import firestore

from app.config import get_settings
from app.firestore import get_db, org_collection, server_timestamp

PreviewAction = Literal["create_import_invoice", "create_service_invoice", "add_product"]


def create(
    org_id: str,
    action: PreviewAction,
    payload: dict[str, Any],
    summary: dict[str, Any],
    actor: str,
) -> str:
    settings = get_settings()
    preview_id = secrets.token_urlsafe(16)
    expires_at = datetime.now(UTC) + timedelta(seconds=settings.preview_ttl_seconds)
    org_collection(org_id, "previews").document(preview_id).set(
        {
            "action": action,
            "payload": payload,
            "summary": summary,
            "actor": actor,
            "created_at": server_timestamp(),
            "expires_at": expires_at,
            "consumed": False,
        }
    )
    return preview_id


def consume(
    org_id: str, preview_id: str, actor: str
) -> tuple[PreviewAction, dict[str, Any]]:
    """Return (action, payload) if valid and unconsumed; raise 400 otherwise.

    We use a transaction so double-consumption under concurrent retries
    produces at most one commit.
    """
    db = get_db()
    ref = org_collection(org_id, "previews").document(preview_id)

    @firestore.transactional
    def _consume(tx: firestore.Transaction) -> tuple[PreviewAction, dict[str, Any]]:
        snap = ref.get(transaction=tx)
        if not snap.exists:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "preview not found")
        data = snap.to_dict() or {}
        if data.get("consumed"):
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "preview already used")
        if data.get("actor") != actor:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "preview belongs to another actor")
        expires_at = data.get("expires_at")
        if isinstance(expires_at, datetime) and expires_at < datetime.now(UTC):
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "preview expired")
        tx.update(ref, {"consumed": True, "consumed_at": server_timestamp()})
        return data["action"], data["payload"]

    return _consume(db.transaction())
