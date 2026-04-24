from __future__ import annotations

from datetime import datetime
from typing import Any

from google.cloud import firestore

from app.firestore import get_db


def get_invoice(invoice_id: str) -> dict[str, Any] | None:
    snap = get_db().collection("invoices").document(invoice_id).get()
    if not snap.exists:
        return None
    return {"id": invoice_id, **(snap.to_dict() or {})}


def list_invoices(
    type_: str | None = None,
    status_: str | None = None,
    from_: datetime | None = None,
    to_: datetime | None = None,
    limit: int = 50,
) -> list[dict[str, Any]]:
    col = get_db().collection("invoices")
    q: firestore.Query = col  # type: ignore[assignment]
    if type_:
        q = q.where("type", "==", type_)
    if status_:
        q = q.where("status", "==", status_)
    if from_:
        q = q.where("created_at", ">=", from_)
    if to_:
        q = q.where("created_at", "<", to_)
    q = q.order_by("created_at", direction=firestore.Query.DESCENDING).limit(limit)
    return [{"id": doc.id, **(doc.to_dict() or {})} for doc in q.stream()]


def list_adjustments_for(invoice_id: str) -> list[dict[str, Any]]:
    q = (
        get_db()
        .collection("adjustments")
        .where("invoice_id", "==", invoice_id)
        .order_by("created_at", direction=firestore.Query.DESCENDING)
    )
    return [{"id": doc.id, **(doc.to_dict() or {})} for doc in q.stream()]
