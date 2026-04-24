from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, Field, StringConstraints, model_validator

from app.models.product import Sku, VndInt

InvoiceType = Literal["import", "service"]
InvoiceStatus = Literal["posted", "adjusted"]
AdjustmentType = Literal["void", "amend"]

Qty = Annotated[int, Field(gt=0, le=100_000)]
Description = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=240)]


# ── Inputs ──────────────────────────────────────────────────────────────

class ImportInvoiceItemIn(BaseModel):
    sku: Sku
    description: Description | None = None  # optional; service layer falls back to product.name
    quantity: Qty
    unit_price: VndInt  # import price per unit


class ImportInvoiceCreate(BaseModel):
    type: Literal["import"] = "import"
    supplier_id: str | None = None
    supplier_name: Annotated[str, StringConstraints(max_length=120)] | None = None
    items: list[ImportInvoiceItemIn] = Field(min_length=1)
    notes: Annotated[str, StringConstraints(max_length=500)] = ""


class ServiceInvoiceItemIn(BaseModel):
    """Either sku (for a product line) or description (for labor).

    If sku is set: we decrement stock and snapshot cost_price from the product.
    If sku is unset: description is required, cost_price is 0 (pure labor).
    """

    sku: Sku | None = None
    description: Description | None = None
    quantity: Qty
    unit_price: VndInt  # selling price per unit (or labor fee per unit)

    @model_validator(mode="after")
    def _require_sku_or_description(self) -> "ServiceInvoiceItemIn":
        if not self.sku and not self.description:
            raise ValueError("service invoice item must have sku or description")
        return self


class ServiceInvoiceCreate(BaseModel):
    type: Literal["service"] = "service"
    customer_id: str | None = None
    customer_name: Annotated[str, StringConstraints(max_length=120)] | None = None
    items: list[ServiceInvoiceItemIn] = Field(min_length=1)
    notes: Annotated[str, StringConstraints(max_length=500)] = ""


# ── Stored shape ────────────────────────────────────────────────────────

class InvoiceLine(BaseModel):
    product_id: str | None = None
    sku: Sku | None = None
    description: str
    quantity: int = Field(gt=0)
    unit_price: VndInt
    cost_price: VndInt  # snapshotted at invoice time
    line_total_revenue: VndInt
    line_total_cost: VndInt


class Invoice(BaseModel):
    id: str
    type: InvoiceType
    status: InvoiceStatus
    created_at: datetime
    created_by: str  # "user:<uid>" | "ai:openclaw"
    supplier_id: str | None = None
    supplier_name: str | None = None
    customer_id: str | None = None
    customer_name: str | None = None
    items: list[InvoiceLine]
    total_revenue: VndInt
    total_cost: VndInt
    profit: int | None = None  # null for import invoices
    notes: str = ""


# ── Adjustments ─────────────────────────────────────────────────────────

class AdjustmentCreate(BaseModel):
    type: AdjustmentType
    reason: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=500)]


class Adjustment(BaseModel):
    id: str
    invoice_id: str
    type: AdjustmentType
    reason: str
    delta_revenue: int
    delta_cost: int
    delta_profit: int | None
    created_at: datetime
    created_by: str
