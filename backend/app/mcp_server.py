"""MCP server — OpenClaw's tool surface.

Mounts as Streamable HTTP at /mcp on the FastAPI app. Every tool wraps a
service-layer function, so the REST and MCP surfaces share the exact same
business logic (one source of truth).

Destructive tools follow the two-phase confirmation pattern:
  1. caller invokes e.g. `create_import_invoice(...)` → we validate + stash
     a preview, return `{preview_id, summary}` without writing
  2. caller invokes `confirm_action(preview_id)` → we commit

This is there specifically to guard against hallucinated or misinterpreted
Zalo messages: OpenClaw must echo the summary to the human before we touch
Firestore."""

from __future__ import annotations

from datetime import date
from typing import Any, Literal

from fastapi import HTTPException, Request, status
from mcp.server.fastmcp import FastMCP
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse
from starlette.types import ASGIApp

from app.auth import Principal
from app.config import get_settings
from app.models.invoice import (
    ImportInvoiceCreate,
    ImportInvoiceItemIn,
    ServiceInvoiceCreate,
    ServiceInvoiceItemIn,
)
from app.models.product import ProductCreate
from app.services import (
    audit,
    customers,
    inventory,
    invoice_read,
    invoices,
    previews,
    reports,
)

AGENT = Principal(actor="agent", uid="openclaw", role="manager")

mcp = FastMCP("garage-ai")


# ── Read-only tools ─────────────────────────────────────────────────────

@mcp.tool()
def get_inventory(query: str | None = None, low_stock_only: bool = False) -> list[dict[str, Any]]:
    """List products. Optionally filter by name/SKU substring or low-stock only.
    Answers: "còn bao nhiêu X?", "hàng nào sắp hết?"."""
    return inventory.list_products(query=query, low_stock_only=low_stock_only)


@mcp.tool()
def get_product(sku: str) -> dict[str, Any]:
    """Look up one product by SKU."""
    p = inventory.get_product(sku.upper())
    if not p:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"no product with SKU {sku}")
    return p


@mcp.tool()
def get_invoice(invoice_id: str) -> dict[str, Any]:
    """Fetch a specific invoice by ID."""
    inv = invoice_read.get_invoice(invoice_id)
    if not inv:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "invoice not found")
    return inv


@mcp.tool()
def get_daily_profit(day: str | None = None) -> dict[str, Any]:
    """Revenue / cost / profit for a single day (Asia/Ho_Chi_Minh).
    `day` is YYYY-MM-DD or null for today. Answers: "hôm nay lời bao nhiêu?"."""
    d = date.fromisoformat(day) if day else None
    return reports.daily(d)


@mcp.tool()
def get_monthly_profit(year: int, month: int) -> dict[str, Any]:
    """Totals for a given year + month. Answers: "tháng này doanh thu bao nhiêu?"."""
    return reports.monthly(year, month)


@mcp.tool()
def get_revenue_summary(from_date: str, to_date: str) -> dict[str, Any]:
    """Revenue / cost / profit across a date range (inclusive). ISO dates."""
    return reports.revenue_summary(date.fromisoformat(from_date), date.fromisoformat(to_date))


@mcp.tool()
def get_top_products(
    period: Literal["day", "week", "month"] = "month", limit: int = 10
) -> list[dict[str, Any]]:
    """Best-sellers by profit contribution. Answers: "dịch vụ/sản phẩm nào lời nhất?"."""
    return reports.top_products(period, limit)


@mcp.tool()
def search_customer(query: str) -> list[dict[str, Any]]:
    """Find a customer by phone substring or name. Returns up to all matches."""
    return customers.search(query)


# ── Destructive tools (two-phase) ───────────────────────────────────────

@mcp.tool()
def add_product(name: str, sku: str, selling_price: int) -> dict[str, Any]:
    """Propose creating a new product. Returns a preview_id — call
    confirm_action(preview_id) to actually create."""
    data = ProductCreate(name=name, sku=sku, selling_price=selling_price)
    summary = {
        "what": "add_product",
        "name": data.name,
        "sku": data.sku,
        "selling_price": data.selling_price,
    }
    pid = previews.create("add_product", data.model_dump(), summary, AGENT.audit_actor)
    audit.log("preview.add_product", AGENT.audit_actor, payload=summary, result={"preview_id": pid})
    return {"preview_id": pid, "summary": summary}


@mcp.tool()
def create_import_invoice(
    items: list[dict[str, Any]],
    supplier_id: str | None = None,
    supplier_name: str | None = None,
    notes: str = "",
) -> dict[str, Any]:
    """Propose an import (stock purchase). `items` = [{sku, quantity, unit_price}].
    Returns preview_id + summary; call confirm_action(preview_id) to commit."""
    parsed_items = [ImportInvoiceItemIn(**i) for i in items]
    data = ImportInvoiceCreate(
        supplier_id=supplier_id,
        supplier_name=supplier_name,
        items=parsed_items,
        notes=notes,
    )
    total = sum(i.quantity * i.unit_price for i in parsed_items)
    summary = {
        "what": "create_import_invoice",
        "supplier": supplier_name or supplier_id,
        "items": [i.model_dump() for i in parsed_items],
        "total_cost": total,
    }
    pid = previews.create("create_import_invoice", data.model_dump(), summary, AGENT.audit_actor)
    audit.log(
        "preview.create_import_invoice", AGENT.audit_actor, payload=summary, result={"preview_id": pid}
    )
    return {"preview_id": pid, "summary": summary}


@mcp.tool()
def create_service_invoice(
    items: list[dict[str, Any]],
    customer_id: str | None = None,
    customer_name: str | None = None,
    notes: str = "",
) -> dict[str, Any]:
    """Propose a service/sales invoice. `items` = [{sku?, description?, quantity, unit_price}].
    Returns preview_id + summary; call confirm_action(preview_id) to commit."""
    parsed_items = [ServiceInvoiceItemIn(**i) for i in items]
    data = ServiceInvoiceCreate(
        customer_id=customer_id,
        customer_name=customer_name,
        items=parsed_items,
        notes=notes,
    )
    total = sum(i.quantity * i.unit_price for i in parsed_items)
    summary = {
        "what": "create_service_invoice",
        "customer": customer_name or customer_id,
        "items": [i.model_dump() for i in parsed_items],
        "total_revenue": total,
    }
    pid = previews.create("create_service_invoice", data.model_dump(), summary, AGENT.audit_actor)
    audit.log(
        "preview.create_service_invoice", AGENT.audit_actor, payload=summary, result={"preview_id": pid}
    )
    return {"preview_id": pid, "summary": summary}


@mcp.tool()
def confirm_action(preview_id: str) -> dict[str, Any]:
    """Commit a previously previewed destructive action."""
    action, payload = previews.consume(preview_id, AGENT.audit_actor)
    if action == "add_product":
        return inventory.create_product(ProductCreate(**payload), AGENT)
    if action == "create_import_invoice":
        parsed = ImportInvoiceCreate(**payload)
        return invoices.create_import_invoice(parsed, AGENT)
    if action == "create_service_invoice":
        parsed = ServiceInvoiceCreate(**payload)
        return invoices.create_service_invoice(parsed, AGENT)
    raise HTTPException(status.HTTP_400_BAD_REQUEST, f"unknown preview action: {action}")


# ── ASGI middleware: API key enforcement ────────────────────────────────

class ApiKeyMiddleware(BaseHTTPMiddleware):
    """Every /mcp/** request must carry a valid X-API-Key header.

    MCP spec permits several auth styles; we pick API-key because OpenClaw is
    the only client and it fits the 'service account' model. The key is
    injected into Cloud Run via Secret Manager.
    """

    async def dispatch(self, request: Request, call_next):  # type: ignore[no-untyped-def, override]
        expected = get_settings().openclaw_api_key
        if request.headers.get("x-api-key") != expected:
            return JSONResponse({"error": "invalid api key"}, status_code=401)
        return await call_next(request)


def mcp_asgi_app() -> ASGIApp:
    """Return the MCP Streamable-HTTP ASGI app, wrapped with API-key auth."""
    inner = mcp.streamable_http_app()
    return ApiKeyMiddleware(inner)  # type: ignore[return-value]
