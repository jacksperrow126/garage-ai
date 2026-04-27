"""Invoice creation — the heart of the system.

All write paths run inside a single Firestore transaction so that:
  - stock changes and avg-cost updates never drift from the invoice record
  - concurrent imports of the same SKU produce a consistent final avg cost
  - a failing stock-deduction (e.g. oversell) aborts the whole invoice

Products are keyed by SKU as the document ID — this lets transactions do
pure doc-reads (no queries), which Firestore handles cleanly.

Moving-average cost uses the spec's formula:

    new_avg = (old_qty * old_avg + delta_qty * delta_unit_price) // new_qty

Integer division loses at most 1 đồng per import; negligible for a small
garage, but worth knowing. See tests/test_invoices.py for drift bounds.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from fastapi import HTTPException, status
from google.cloud import firestore
from google.cloud.firestore_v1 import DocumentReference

from app.auth import Principal
from app.firestore import get_db, org_collection, server_timestamp
from app.models.invoice import (
    ImportInvoiceCreate,
    ServiceInvoiceCreate,
)
from app.services import audit


# ── Helpers ─────────────────────────────────────────────────────────────

def _product_ref(org_id: str, sku: str) -> DocumentReference:
    return org_collection(org_id, "products").document(sku)


def _invoice_ref(org_id: str) -> DocumentReference:
    return org_collection(org_id, "invoices").document()


def _stock_move(
    org_id: str,
    tx: firestore.Transaction,
    *,
    product_id: str,
    sku: str,
    delta: int,
    reason: str,
    invoice_id: str,
    qty_before: int,
    qty_after: int,
    avg_cost_before: int,
    avg_cost_after: int,
    actor: str,
) -> None:
    ref = org_collection(org_id, "stock_moves").document()
    tx.set(
        ref,
        {
            "product_id": product_id,
            "sku": sku,
            "delta": delta,
            "reason": reason,
            "invoice_id": invoice_id,
            "qty_before": qty_before,
            "qty_after": qty_after,
            "avg_cost_before": avg_cost_before,
            "avg_cost_after": avg_cost_after,
            "created_at": server_timestamp(),
            "created_by": actor,
        },
    )


# ── Import invoice ──────────────────────────────────────────────────────

def create_import_invoice(
    org_id: str, data: ImportInvoiceCreate, principal: Principal
) -> dict[str, Any]:
    db = get_db()
    invoice_ref = _invoice_ref(org_id)
    product_refs = [_product_ref(org_id, item.sku) for item in data.items]
    actor = principal.audit_actor

    @firestore.transactional
    def _tx(tx: firestore.Transaction) -> dict[str, Any]:
        # ── READS first (Firestore transaction rule) ──
        snaps = [ref.get(transaction=tx) for ref in product_refs]

        missing = [item.sku for item, snap in zip(data.items, snaps, strict=True) if not snap.exists]
        if missing:
            raise HTTPException(
                status.HTTP_404_NOT_FOUND,
                f"unknown SKU(s): {', '.join(missing)}",
            )

        # ── COMPUTE per item ──
        now_lines: list[dict[str, Any]] = []
        product_updates: list[tuple[DocumentReference, dict[str, Any], dict[str, int]]] = []
        total_cost = 0

        for item, ref, snap in zip(data.items, product_refs, snaps, strict=True):
            p = snap.to_dict() or {}
            old_qty = int(p.get("quantity", 0))
            old_avg = int(p.get("average_cost", 0))
            new_qty = old_qty + item.quantity
            new_avg = (old_qty * old_avg + item.quantity * item.unit_price) // new_qty

            line_cost = item.quantity * item.unit_price
            total_cost += line_cost

            now_lines.append(
                {
                    "product_id": item.sku,
                    "sku": item.sku,
                    "description": item.description or p.get("name", item.sku),
                    "quantity": item.quantity,
                    "unit_price": item.unit_price,
                    "cost_price": item.unit_price,
                    "line_total_revenue": line_cost,
                    "line_total_cost": line_cost,
                }
            )
            product_updates.append(
                (
                    ref,
                    {
                        "quantity": new_qty,
                        "average_cost": new_avg,
                        "last_import_price": item.unit_price,
                        "updated_at": server_timestamp(),
                    },
                    {
                        "qty_before": old_qty,
                        "qty_after": new_qty,
                        "avg_cost_before": old_avg,
                        "avg_cost_after": new_avg,
                    },
                )
            )

        # ── WRITES ──
        for ref, update, _ in product_updates:
            tx.update(ref, update)

        for item, (_, _, mv) in zip(data.items, product_updates, strict=True):
            _stock_move(
                org_id,
                tx,
                product_id=item.sku,
                sku=item.sku,
                delta=item.quantity,
                reason="import",
                invoice_id=invoice_ref.id,
                qty_before=mv["qty_before"],
                qty_after=mv["qty_after"],
                avg_cost_before=mv["avg_cost_before"],
                avg_cost_after=mv["avg_cost_after"],
                actor=actor,
            )

        now = datetime.now(UTC)
        invoice_doc = {
            "type": "import",
            "status": "posted",
            "created_by": actor,
            "supplier_id": data.supplier_id,
            "supplier_name": data.supplier_name,
            "customer_id": None,
            "customer_name": None,
            "items": now_lines,
            "total_revenue": total_cost,
            "total_cost": total_cost,
            "profit": None,
            "notes": data.notes,
        }
        tx.set(invoice_ref, {**invoice_doc, "created_at": server_timestamp()})

        audit.log(
            org_id,
            "create_import_invoice",
            actor,
            payload={"supplier": data.supplier_name, "items": [i.model_dump() for i in data.items]},
            result={"invoice_id": invoice_ref.id, "total_cost": total_cost},
            tx=tx,
        )

        return {"id": invoice_ref.id, **invoice_doc, "created_at": now}

    return _tx(db.transaction())


# ── Service invoice (sale / repair) ─────────────────────────────────────

def create_service_invoice(
    org_id: str, data: ServiceInvoiceCreate, principal: Principal
) -> dict[str, Any]:
    db = get_db()
    invoice_ref = _invoice_ref(org_id)
    actor = principal.audit_actor

    product_skus = [item.sku for item in data.items if item.sku]
    product_refs = {sku: _product_ref(org_id, sku) for sku in product_skus}

    @firestore.transactional
    def _tx(tx: firestore.Transaction) -> dict[str, Any]:
        snaps = {sku: ref.get(transaction=tx) for sku, ref in product_refs.items()}
        missing = [sku for sku, snap in snaps.items() if not snap.exists]
        if missing:
            raise HTTPException(
                status.HTTP_404_NOT_FOUND,
                f"unknown SKU(s): {', '.join(missing)}",
            )

        now_lines: list[dict[str, Any]] = []
        stock_updates: dict[str, dict[str, int]] = {}

        total_revenue = 0
        total_cost = 0

        for item in data.items:
            if item.sku:
                p = snaps[item.sku].to_dict() or {}
                old_qty = int(p.get("quantity", 0))
                old_avg = int(p.get("average_cost", 0))
                if old_qty < item.quantity:
                    raise HTTPException(
                        status.HTTP_400_BAD_REQUEST,
                        f"insufficient stock for {item.sku}: have {old_qty}, need {item.quantity}",
                    )
                new_qty = old_qty - item.quantity
                cost_price = old_avg
                line_revenue = item.quantity * item.unit_price
                line_cost = item.quantity * cost_price

                now_lines.append(
                    {
                        "product_id": item.sku,
                        "sku": item.sku,
                        "description": item.description or p.get("name", item.sku),
                        "quantity": item.quantity,
                        "unit_price": item.unit_price,
                        "cost_price": cost_price,
                        "line_total_revenue": line_revenue,
                        "line_total_cost": line_cost,
                    }
                )
                stock_updates[item.sku] = {
                    "old_qty": old_qty,
                    "new_qty": new_qty,
                    "old_avg": old_avg,
                    "new_avg": old_avg,
                }
                total_revenue += line_revenue
                total_cost += line_cost
            else:
                line_revenue = item.quantity * item.unit_price
                assert item.description is not None
                now_lines.append(
                    {
                        "product_id": None,
                        "sku": None,
                        "description": item.description,
                        "quantity": item.quantity,
                        "unit_price": item.unit_price,
                        "cost_price": 0,
                        "line_total_revenue": line_revenue,
                        "line_total_cost": 0,
                    }
                )
                total_revenue += line_revenue

        for sku, mv in stock_updates.items():
            tx.update(
                product_refs[sku],
                {"quantity": mv["new_qty"], "updated_at": server_timestamp()},
            )

        for item in data.items:
            if not item.sku:
                continue
            mv = stock_updates[item.sku]
            _stock_move(
                org_id,
                tx,
                product_id=item.sku,
                sku=item.sku,
                delta=-item.quantity,
                reason="sale",
                invoice_id=invoice_ref.id,
                qty_before=mv["old_qty"],
                qty_after=mv["new_qty"],
                avg_cost_before=mv["old_avg"],
                avg_cost_after=mv["new_avg"],
                actor=actor,
            )

        now = datetime.now(UTC)
        invoice_doc = {
            "type": "service",
            "status": "posted",
            "created_by": actor,
            "supplier_id": None,
            "supplier_name": None,
            "customer_id": data.customer_id,
            "customer_name": data.customer_name,
            "items": now_lines,
            "total_revenue": total_revenue,
            "total_cost": total_cost,
            "profit": total_revenue - total_cost,
            "notes": data.notes,
        }
        tx.set(invoice_ref, {**invoice_doc, "created_at": server_timestamp()})

        audit.log(
            org_id,
            "create_service_invoice",
            actor,
            payload={
                "customer": data.customer_name or data.customer_id,
                "items": [i.model_dump() for i in data.items],
            },
            result={
                "invoice_id": invoice_ref.id,
                "revenue": total_revenue,
                "cost": total_cost,
                "profit": total_revenue - total_cost,
            },
            tx=tx,
        )
        return {"id": invoice_ref.id, **invoice_doc, "created_at": now}

    return _tx(db.transaction())


# ── Adjustments ─────────────────────────────────────────────────────────

def create_adjustment(
    org_id: str, invoice_id: str, adj_type: str, reason: str, principal: Principal
) -> dict[str, Any]:
    """V1 adjustment model is record-only: marks the original invoice as
    `adjusted` and writes an `adjustments/` doc with the reason."""
    db = get_db()
    inv_ref = org_collection(org_id, "invoices").document(invoice_id)
    adj_ref = org_collection(org_id, "adjustments").document()
    actor = principal.audit_actor

    @firestore.transactional
    def _tx(tx: firestore.Transaction) -> dict[str, Any]:
        snap = inv_ref.get(transaction=tx)
        if not snap.exists:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "invoice not found")

        now = datetime.now(UTC)
        adj_doc = {
            "invoice_id": invoice_id,
            "type": adj_type,
            "reason": reason,
            "delta_revenue": 0,
            "delta_cost": 0,
            "delta_profit": None,
            "created_by": actor,
        }
        tx.set(adj_ref, {**adj_doc, "created_at": server_timestamp()})
        tx.update(inv_ref, {"status": "adjusted"})

        audit.log(
            org_id,
            "create_adjustment",
            actor,
            payload={"invoice_id": invoice_id, "type": adj_type, "reason": reason},
            result={"adjustment_id": adj_ref.id},
            tx=tx,
        )
        return {"id": adj_ref.id, **adj_doc, "created_at": now}

    return _tx(db.transaction())
