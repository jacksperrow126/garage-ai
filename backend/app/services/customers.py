from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from fastapi import HTTPException, status
from google.cloud import firestore

from app.auth import Principal
from app.firestore import org_collection, server_timestamp
from app.models.customer import CustomerCreate, CustomerUpdate
from app.services import audit


def _ref(org_id: str, customer_id: str) -> firestore.DocumentReference:
    return org_collection(org_id, "customers").document(customer_id)


def create(org_id: str, data: CustomerCreate, principal: Principal) -> dict[str, Any]:
    ref = org_collection(org_id, "customers").document()
    now = datetime.now(UTC)
    ref.set({**data.model_dump(), "created_at": server_timestamp()})
    audit.log(
        org_id,
        "create_customer",
        principal.audit_actor,
        payload=data.model_dump(),
        result={"id": ref.id},
    )
    return {"id": ref.id, **data.model_dump(), "created_at": now}


def get(org_id: str, customer_id: str) -> dict[str, Any] | None:
    snap = _ref(org_id, customer_id).get()
    if not snap.exists:
        return None
    return {"id": customer_id, **(snap.to_dict() or {})}


def list_all(org_id: str) -> list[dict[str, Any]]:
    return [
        {"id": doc.id, **(doc.to_dict() or {})}
        for doc in org_collection(org_id, "customers").stream()
    ]


def update(
    org_id: str, customer_id: str, data: CustomerUpdate, principal: Principal
) -> dict[str, Any]:
    ref = _ref(org_id, customer_id)
    snap = ref.get()
    if not snap.exists:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "customer not found")
    updates = data.model_dump(exclude_none=True)
    if not updates:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "no fields to update")
    ref.update(updates)
    audit.log(
        org_id,
        "update_customer",
        principal.audit_actor,
        payload={"id": customer_id, "fields": updates},
        result={"id": customer_id},
    )
    return {"id": customer_id, **(snap.to_dict() or {}), **updates}


def delete(org_id: str, customer_id: str, principal: Principal) -> None:
    _ref(org_id, customer_id).delete()
    audit.log(
        org_id,
        "delete_customer",
        principal.audit_actor,
        payload={"id": customer_id},
        result={"id": customer_id},
    )


def search(org_id: str, query: str) -> list[dict[str, Any]]:
    """Substring match over name + phone. Small dataset — fine to scan."""
    needle = query.strip().lower()
    if not needle:
        return []
    return [
        c
        for c in list_all(org_id)
        if needle in (c.get("name") or "").lower() or needle in (c.get("phone") or "")
    ]


def history(org_id: str, customer_id: str) -> list[dict[str, Any]]:
    col = org_collection(org_id, "invoices")
    q = col.where("customer_id", "==", customer_id).order_by(
        "created_at", direction=firestore.Query.DESCENDING
    )
    return [{"id": doc.id, **(doc.to_dict() or {})} for doc in q.stream()]
