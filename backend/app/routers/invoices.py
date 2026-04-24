from datetime import datetime
from typing import Annotated, Literal

from fastapi import APIRouter, Body, Depends, HTTPException, Query, status
from pydantic import Field

from app.auth import Principal, require_agent_or_user
from app.models.invoice import (
    AdjustmentCreate,
    ImportInvoiceCreate,
    ServiceInvoiceCreate,
)
from app.services import invoice_read, invoices

router = APIRouter(prefix="/invoices", tags=["invoices"])

InvoiceBody = Annotated[
    ImportInvoiceCreate | ServiceInvoiceCreate,
    Field(discriminator="type"),
]


@router.get("")
def list_invoices(
    type: Literal["import", "service"] | None = Query(default=None),
    status_: Literal["posted", "adjusted"] | None = Query(default=None, alias="status"),
    from_: datetime | None = Query(default=None, alias="from"),
    to: datetime | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    _: Principal = Depends(require_agent_or_user),
) -> list[dict]:
    return invoice_read.list_invoices(
        type_=type, status_=status_, from_=from_, to_=to, limit=limit
    )


@router.get("/{invoice_id}")
def get_invoice(
    invoice_id: str,
    _: Principal = Depends(require_agent_or_user),
) -> dict:
    inv = invoice_read.get_invoice(invoice_id)
    if not inv:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "invoice not found")
    inv["adjustments"] = invoice_read.list_adjustments_for(invoice_id)
    return inv


@router.post("", status_code=status.HTTP_201_CREATED)
def create_invoice(
    payload: InvoiceBody = Body(...),
    principal: Principal = Depends(require_agent_or_user),
) -> dict:
    if payload.type == "import":
        return invoices.create_import_invoice(payload, principal)
    return invoices.create_service_invoice(payload, principal)


@router.post("/{invoice_id}/adjustments", status_code=status.HTTP_201_CREATED)
def create_adjustment(
    invoice_id: str,
    data: AdjustmentCreate,
    principal: Principal = Depends(require_agent_or_user),
) -> dict:
    return invoices.create_adjustment(invoice_id, data.type, data.reason, principal)
