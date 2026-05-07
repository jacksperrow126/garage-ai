from datetime import datetime
from typing import Annotated, Literal

from fastapi import APIRouter, Body, Depends, HTTPException, Query, Response, status
from pydantic import Field

from app.auth import Principal, require_agent_or_user, require_org_id, require_user
from app.models.invoice import (
    AdjustmentCreate,
    ImportInvoiceCreate,
    ServiceInvoiceCreate,
)
from app.services import (
    customers as customers_service,
    invoice_pdf,
    invoice_read,
    invoices,
    orgs as orgs_service,
    suppliers as suppliers_service,
)

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
    org_id: str = Depends(require_org_id),
) -> list[dict]:
    return invoice_read.list_invoices(
        org_id, type_=type, status_=status_, from_=from_, to_=to, limit=limit
    )


@router.get("/{invoice_id}")
def get_invoice(
    invoice_id: str,
    _: Principal = Depends(require_agent_or_user),
    org_id: str = Depends(require_org_id),
) -> dict:
    inv = invoice_read.get_invoice(org_id, invoice_id)
    if not inv:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "invoice not found")
    inv["adjustments"] = invoice_read.list_adjustments_for(org_id, invoice_id)
    return inv


@router.post("", status_code=status.HTTP_201_CREATED)
def create_invoice(
    payload: InvoiceBody = Body(...),
    principal: Principal = Depends(require_agent_or_user),
    org_id: str = Depends(require_org_id),
) -> dict:
    if payload.type == "import":
        return invoices.create_import_invoice(org_id, payload, principal)
    return invoices.create_service_invoice(org_id, payload, principal)


@router.get("/{invoice_id}/pdf")
def download_invoice_pdf(
    invoice_id: str,
    _: Principal = Depends(require_user),
    org_id: str = Depends(require_org_id),
) -> Response:
    """Render a customer-facing invoice PDF (A5). Browser-triggers a
    download via the Content-Disposition header. Auth is user-only —
    we don't expose this to the agent because the agent already has
    the structured invoice data via MCP."""
    inv = invoice_read.get_invoice(org_id, invoice_id)
    if not inv:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "invoice not found")
    org = orgs_service.get_org(org_id)
    if not org:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "org not found")
    customer = (
        customers_service.get(org_id, inv["customer_id"])
        if inv.get("customer_id")
        else None
    )
    supplier = (
        suppliers_service.get(org_id, inv["supplier_id"])
        if inv.get("supplier_id")
        else None
    )
    pdf_bytes = invoice_pdf.render_invoice_pdf(
        org, inv, customer=customer, supplier=supplier
    )
    filename = f"hoa-don-{invoice_id}.pdf"
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.post("/{invoice_id}/adjustments", status_code=status.HTTP_201_CREATED)
def create_adjustment(
    invoice_id: str,
    data: AdjustmentCreate,
    principal: Principal = Depends(require_agent_or_user),
    org_id: str = Depends(require_org_id),
) -> dict:
    return invoices.create_adjustment(org_id, invoice_id, data.type, data.reason, principal)
