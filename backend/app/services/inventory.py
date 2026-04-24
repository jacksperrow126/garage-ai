"""Product CRUD + listing. Stock mutations don't live here — those flow
through invoices (import = +N, service = -N) so that every change is tied
to an invoice + stock_move + audit_log, not a free-standing endpoint.

The only stock-mutating operation here is `manual_correction`, deliberately
gated to the `owner` role — it's the break-glass path for physical recounts
and will appear in audit_logs as action="manual_correction"."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from fastapi import HTTPException, status
from google.cloud import firestore

from app.auth import Principal
from app.config import get_settings
from app.firestore import get_db, server_timestamp
from app.models.product import ProductCreate, ProductUpdate
from app.services import audit


def _product_ref(sku: str) -> firestore.DocumentReference:
    return get_db().collection("products").document(sku)


def create_product(data: ProductCreate, principal: Principal) -> dict[str, Any]:
    ref = _product_ref(data.sku)
    actor = principal.audit_actor

    @firestore.transactional
    def _tx(tx: firestore.Transaction) -> dict[str, Any]:
        snap = ref.get(transaction=tx)
        if snap.exists:
            raise HTTPException(status.HTTP_409_CONFLICT, f"SKU {data.sku} already exists")
        doc = {
            "name": data.name,
            "sku": data.sku,
            "quantity": 0,
            "selling_price": data.selling_price,
            "average_cost": 0,
            "last_import_price": 0,
            "active": True,
            "created_at": server_timestamp(),
            "updated_at": server_timestamp(),
        }
        tx.set(ref, doc)
        audit.log(
            "add_product",
            actor,
            payload=data.model_dump(),
            result={"sku": data.sku},
            tx=tx,
        )
        return {"id": data.sku, **doc}

    return _tx(get_db().transaction())


def update_product(sku: str, data: ProductUpdate, principal: Principal) -> dict[str, Any]:
    ref = _product_ref(sku)
    actor = principal.audit_actor
    updates = data.model_dump(exclude_none=True)
    if not updates:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "no fields to update")
    updates["updated_at"] = server_timestamp()

    @firestore.transactional
    def _tx(tx: firestore.Transaction) -> dict[str, Any]:
        snap = ref.get(transaction=tx)
        if not snap.exists:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "product not found")
        tx.update(ref, updates)
        audit.log(
            "update_product",
            actor,
            payload={"sku": sku, "fields": updates},
            result={"sku": sku},
            tx=tx,
        )
        return {"id": sku, **(snap.to_dict() or {}), **updates}

    return _tx(get_db().transaction())


def get_product(sku: str) -> dict[str, Any] | None:
    snap = _product_ref(sku).get()
    if not snap.exists:
        return None
    return {"id": sku, **(snap.to_dict() or {})}


def list_products(query: str | None = None, low_stock_only: bool = False) -> list[dict[str, Any]]:
    settings = get_settings()
    col = get_db().collection("products")
    q: firestore.Query = col  # type: ignore[assignment]
    if low_stock_only:
        q = q.where("quantity", "<=", settings.low_stock_threshold)
    rows = [{"id": doc.id, **(doc.to_dict() or {})} for doc in q.stream()]
    if query:
        needle = query.strip().lower()
        rows = [r for r in rows if needle in r["name"].lower() or needle in r["sku"].lower()]
    return rows


def manual_correction(
    sku: str, new_quantity: int, reason: str, principal: Principal
) -> dict[str, Any]:
    """Owner-only break-glass stock correction (physical recount). Does NOT
    change avg_cost — corrections adjust the head-count without implying a
    new cost basis. Logged as reason='manual' in stock_moves."""
    if principal.role != "owner":
        raise HTTPException(status.HTTP_403_FORBIDDEN, "owner role required")
    if new_quantity < 0:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "quantity must be >= 0")

    ref = _product_ref(sku)
    move_ref = get_db().collection("stock_moves").document()
    actor = principal.audit_actor

    @firestore.transactional
    def _tx(tx: firestore.Transaction) -> dict[str, Any]:
        snap = ref.get(transaction=tx)
        if not snap.exists:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "product not found")
        p = snap.to_dict() or {}
        old_qty = int(p.get("quantity", 0))
        avg = int(p.get("average_cost", 0))
        delta = new_quantity - old_qty

        tx.update(ref, {"quantity": new_quantity, "updated_at": server_timestamp()})
        tx.set(
            move_ref,
            {
                "product_id": sku,
                "sku": sku,
                "delta": delta,
                "reason": "manual",
                "invoice_id": None,
                "qty_before": old_qty,
                "qty_after": new_quantity,
                "avg_cost_before": avg,
                "avg_cost_after": avg,
                "created_at": server_timestamp(),
                "created_by": actor,
                "note": reason,
            },
        )
        audit.log(
            "manual_correction",
            actor,
            payload={"sku": sku, "new_quantity": new_quantity, "reason": reason},
            result={"delta": delta},
            tx=tx,
        )
        return {"id": sku, "quantity": new_quantity, "delta": delta}

    return _tx(get_db().transaction())
