from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from fastapi import HTTPException, status
from google.cloud import firestore

from app.auth import Principal
from app.firestore import org_collection, server_timestamp
from app.models.supplier import SupplierCreate, SupplierUpdate
from app.services import audit


def _ref(org_id: str, supplier_id: str) -> firestore.DocumentReference:
    return org_collection(org_id, "suppliers").document(supplier_id)


def create(org_id: str, data: SupplierCreate, principal: Principal) -> dict[str, Any]:
    ref = org_collection(org_id, "suppliers").document()
    now = datetime.now(UTC)
    ref.set({**data.model_dump(), "created_at": server_timestamp()})
    audit.log(
        org_id,
        "create_supplier",
        principal.audit_actor,
        payload=data.model_dump(),
        result={"id": ref.id},
    )
    return {"id": ref.id, **data.model_dump(), "created_at": now}


def get(org_id: str, supplier_id: str) -> dict[str, Any] | None:
    snap = _ref(org_id, supplier_id).get()
    if not snap.exists:
        return None
    return {"id": supplier_id, **(snap.to_dict() or {})}


def list_all(org_id: str) -> list[dict[str, Any]]:
    return [
        {"id": doc.id, **(doc.to_dict() or {})}
        for doc in org_collection(org_id, "suppliers").stream()
    ]


def update(
    org_id: str, supplier_id: str, data: SupplierUpdate, principal: Principal
) -> dict[str, Any]:
    ref = _ref(org_id, supplier_id)
    snap = ref.get()
    if not snap.exists:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "supplier not found")
    updates = data.model_dump(exclude_none=True)
    if not updates:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "no fields to update")
    ref.update(updates)
    audit.log(
        org_id,
        "update_supplier",
        principal.audit_actor,
        payload={"id": supplier_id, "fields": updates},
        result={"id": supplier_id},
    )
    return {"id": supplier_id, **(snap.to_dict() or {}), **updates}


def delete(org_id: str, supplier_id: str, principal: Principal) -> None:
    _ref(org_id, supplier_id).delete()
    audit.log(
        org_id,
        "delete_supplier",
        principal.audit_actor,
        payload={"id": supplier_id},
        result={"id": supplier_id},
    )
