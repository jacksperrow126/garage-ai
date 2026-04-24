from __future__ import annotations

from typing import Any

from fastapi import HTTPException, status
from google.cloud import firestore

from app.auth import Principal
from app.firestore import get_db, server_timestamp
from app.models.customer import CustomerCreate, CustomerUpdate
from app.services import audit


def _ref(customer_id: str) -> firestore.DocumentReference:
    return get_db().collection("customers").document(customer_id)


def create(data: CustomerCreate, principal: Principal) -> dict[str, Any]:
    ref = get_db().collection("customers").document()
    doc = {**data.model_dump(), "created_at": server_timestamp()}
    ref.set(doc)
    audit.log("create_customer", principal.audit_actor, payload=data.model_dump(), result={"id": ref.id})
    return {"id": ref.id, **doc}


def get(customer_id: str) -> dict[str, Any] | None:
    snap = _ref(customer_id).get()
    if not snap.exists:
        return None
    return {"id": customer_id, **(snap.to_dict() or {})}


def list_all() -> list[dict[str, Any]]:
    return [
        {"id": doc.id, **(doc.to_dict() or {})}
        for doc in get_db().collection("customers").stream()
    ]


def update(customer_id: str, data: CustomerUpdate, principal: Principal) -> dict[str, Any]:
    ref = _ref(customer_id)
    snap = ref.get()
    if not snap.exists:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "customer not found")
    updates = data.model_dump(exclude_none=True)
    if not updates:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "no fields to update")
    ref.update(updates)
    audit.log(
        "update_customer",
        principal.audit_actor,
        payload={"id": customer_id, "fields": updates},
        result={"id": customer_id},
    )
    return {"id": customer_id, **(snap.to_dict() or {}), **updates}


def delete(customer_id: str, principal: Principal) -> None:
    _ref(customer_id).delete()
    audit.log(
        "delete_customer",
        principal.audit_actor,
        payload={"id": customer_id},
        result={"id": customer_id},
    )


def search(query: str) -> list[dict[str, Any]]:
    """Substring match over name + phone. Small dataset — fine to scan.
    Tight optimization can wait until there are thousands of customers."""
    needle = query.strip().lower()
    if not needle:
        return []
    return [
        c
        for c in list_all()
        if needle in (c.get("name") or "").lower() or needle in (c.get("phone") or "")
    ]


def history(customer_id: str) -> list[dict[str, Any]]:
    col = get_db().collection("invoices")
    q = col.where("customer_id", "==", customer_id).order_by(
        "created_at", direction=firestore.Query.DESCENDING
    )
    return [{"id": doc.id, **(doc.to_dict() or {})} for doc in q.stream()]
