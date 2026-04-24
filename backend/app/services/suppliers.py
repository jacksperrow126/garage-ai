from __future__ import annotations

from typing import Any

from fastapi import HTTPException, status
from google.cloud import firestore

from app.auth import Principal
from app.firestore import get_db, server_timestamp
from app.models.supplier import SupplierCreate, SupplierUpdate
from app.services import audit


def _ref(supplier_id: str) -> firestore.DocumentReference:
    return get_db().collection("suppliers").document(supplier_id)


def create(data: SupplierCreate, principal: Principal) -> dict[str, Any]:
    ref = get_db().collection("suppliers").document()
    doc = {**data.model_dump(), "created_at": server_timestamp()}
    ref.set(doc)
    audit.log("create_supplier", principal.audit_actor, payload=data.model_dump(), result={"id": ref.id})
    return {"id": ref.id, **doc}


def get(supplier_id: str) -> dict[str, Any] | None:
    snap = _ref(supplier_id).get()
    if not snap.exists:
        return None
    return {"id": supplier_id, **(snap.to_dict() or {})}


def list_all() -> list[dict[str, Any]]:
    return [
        {"id": doc.id, **(doc.to_dict() or {})}
        for doc in get_db().collection("suppliers").stream()
    ]


def update(supplier_id: str, data: SupplierUpdate, principal: Principal) -> dict[str, Any]:
    ref = _ref(supplier_id)
    snap = ref.get()
    if not snap.exists:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "supplier not found")
    updates = data.model_dump(exclude_none=True)
    if not updates:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "no fields to update")
    ref.update(updates)
    audit.log(
        "update_supplier",
        principal.audit_actor,
        payload={"id": supplier_id, "fields": updates},
        result={"id": supplier_id},
    )
    return {"id": supplier_id, **(snap.to_dict() or {}), **updates}


def delete(supplier_id: str, principal: Principal) -> None:
    _ref(supplier_id).delete()
    audit.log(
        "delete_supplier",
        principal.audit_actor,
        payload={"id": supplier_id},
        result={"id": supplier_id},
    )
