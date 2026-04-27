from __future__ import annotations

from datetime import datetime
from typing import Any

from google.cloud import firestore

from app.firestore import org_collection


def get_invoice(org_id: str, invoice_id: str) -> dict[str, Any] | None:
    snap = org_collection(org_id, "invoices").document(invoice_id).get()
    if not snap.exists:
        return None
    return {"id": invoice_id, **(snap.to_dict() or {})}


def list_invoices(
    org_id: str,
    type_: str | None = None,
    status_: str | None = None,
    from_: datetime | None = None,
    to_: datetime | None = None,
    limit: int = 50,
) -> list[dict[str, Any]]:
    col = org_collection(org_id, "invoices")
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


def list_adjustments_for(org_id: str, invoice_id: str) -> list[dict[str, Any]]:
    q = (
        org_collection(org_id, "adjustments")
        .where("invoice_id", "==", invoice_id)
        .order_by("created_at", direction=firestore.Query.DESCENDING)
    )
    return [{"id": doc.id, **(doc.to_dict() or {})} for doc in q.stream()]
