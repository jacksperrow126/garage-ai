"""Two-phase confirmation for destructive MCP tools.

Flow:
  1. OpenClaw calls e.g. `create_import_invoice(...)` → we validate the input,
     stash it under a UUID, and return `{preview_id, summary}` WITHOUT writing.
  2. OpenClaw shows the summary to the user in Zalo ("you're about to import
     5 × OIL5W30 @ 180k = 900k, ok?").
  3. OpenClaw calls `confirm_action(preview_id)` and we commit.

Previews are stored in Firestore (not in-memory) so they survive Cloud Run
scale-to-zero and multi-instance deploys. `expires_at` is a timestamp field
Firestore TTL policy can clean up; worst case we filter by it on read.
"""

from __future__ import annotations

import secrets
from datetime import UTC, datetime, timedelta
from typing import Any, Literal

from fastapi import HTTPException, status
from google.cloud import firestore

from app.config import get_settings
from app.firestore import get_db, server_timestamp

PreviewAction = Literal["create_import_invoice", "create_service_invoice", "add_product"]


def create(action: PreviewAction, payload: dict[str, Any], summary: dict[str, Any], actor: str) -> str:
    settings = get_settings()
    preview_id = secrets.token_urlsafe(16)
    expires_at = datetime.now(UTC) + timedelta(seconds=settings.preview_ttl_seconds)
    get_db().collection("previews").document(preview_id).set(
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


def consume(preview_id: str, actor: str) -> tuple[PreviewAction, dict[str, Any]]:
    """Return (action, payload) if valid and unconsumed; raise 400 otherwise.

    We use a transaction so double-consumption under concurrent retries
    produces at most one commit.
    """
    db = get_db()
    ref = db.collection("previews").document(preview_id)

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
