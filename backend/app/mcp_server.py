"""MCP server — the bot's tool surface.

Mounts as Streamable HTTP at /mcp on the FastAPI app. Every tool wraps a
service-layer function, so the REST and MCP surfaces share the exact same
business logic (one source of truth).

Each tool takes `org_id` as the first argument. The agent's system prompt
instructs Claude to thread the calling user's org_id through every tool;
the MCP middleware uses a single shared bearer token so per-call identity
isn't propagated, and the LLM's prompt-following is what makes routing
right. This is acceptable while we have one admin and one shop trust
boundary; revisit if the bot ever hosts truly untrusted shops.

Destructive tools follow the two-phase confirmation pattern:
  1. caller invokes e.g. `create_import_invoice(...)` → we validate + stash
     a preview, return `{preview_id, summary}` without writing
  2. caller invokes `confirm_action(preview_id)` → we commit
"""

from __future__ import annotations

from datetime import date
from typing import Any, Literal

from fastapi import HTTPException, Request, status
from mcp.server.fastmcp import FastMCP
from mcp.server.transport_security import TransportSecuritySettings
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

mcp = FastMCP(
    "garage-ai",
    streamable_http_path="/",
    transport_security=TransportSecuritySettings(
        allowed_hosts=[
            "127.0.0.1:*",
            "localhost:*",
            "[::1]:*",
            "*.run.app",
            "garage-ai-api-969667367100.asia-southeast1.run.app",
        ],
        allowed_origins=[
            "http://127.0.0.1:*",
            "http://localhost:*",
            "http://[::1]:*",
            "https://garage-ai-api-969667367100.asia-southeast1.run.app",
            "https://garage-ai-admin--garage-manager-ai.asia-southeast1.hosted.app",
        ],
    ),
)


# ── Read-only tools ─────────────────────────────────────────────────────

@mcp.tool()
def get_inventory(
    org_id: str, query: str | None = None, low_stock_only: bool = False
) -> list[dict[str, Any]]:
    """List products in the given org. Optionally filter by name/SKU
    substring or low-stock only. Answers: "còn bao nhiêu X?", "hàng nào sắp hết?"."""
    return inventory.list_products(org_id, query=query, low_stock_only=low_stock_only)


@mcp.tool()
def get_product(org_id: str, sku: str) -> dict[str, Any]:
    """Look up one product by SKU within the given org."""
    p = inventory.get_product(org_id, sku.upper())
    if not p:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"no product with SKU {sku}")
    return p


@mcp.tool()
def get_invoice(org_id: str, invoice_id: str) -> dict[str, Any]:
    """Fetch a specific invoice by ID within the given org."""
    inv = invoice_read.get_invoice(org_id, invoice_id)
    if not inv:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "invoice not found")
    return inv


@mcp.tool()
def get_daily_profit(org_id: str, day: str | None = None) -> dict[str, Any]:
    """Revenue / cost / profit for a single day (Asia/Ho_Chi_Minh).
    `day` is YYYY-MM-DD or null for today. Answers: "hôm nay lời bao nhiêu?"."""
    d = date.fromisoformat(day) if day else None
    return reports.daily(org_id, d)


@mcp.tool()
def get_monthly_profit(org_id: str, year: int, month: int) -> dict[str, Any]:
    """Totals for a given year + month. Answers: "tháng này doanh thu bao nhiêu?"."""
    return reports.monthly(org_id, year, month)


@mcp.tool()
def get_revenue_summary(
    org_id: str, from_date: str, to_date: str
) -> dict[str, Any]:
    """Revenue / cost / profit across a date range (inclusive). ISO dates."""
    return reports.revenue_summary(
        org_id, date.fromisoformat(from_date), date.fromisoformat(to_date)
    )


@mcp.tool()
def get_top_products(
    org_id: str,
    period: Literal["day", "week", "month"] = "month",
    limit: int = 10,
) -> list[dict[str, Any]]:
    """Best-sellers by profit contribution. Answers: "dịch vụ/sản phẩm nào lời nhất?"."""
    return reports.top_products(org_id, period, limit)


@mcp.tool()
def search_customer(org_id: str, query: str) -> list[dict[str, Any]]:
    """Find a customer in the given org by phone substring or name."""
    return customers.search(org_id, query)


# ── Destructive tools (two-phase) ───────────────────────────────────────

@mcp.tool()
def add_product(
    org_id: str,
    name: str,
    selling_price: int,
    sku: str | None = None,
) -> dict[str, Any]:
    """Propose creating a new product. SKU is optional — if omitted it's
    auto-derived from the name at confirm time. Returns a preview_id —
    call confirm_action(org_id, preview_id) to actually create."""
    data = ProductCreate(name=name, sku=sku, selling_price=selling_price)
    summary = {
        "what": "add_product",
        "name": data.name,
        "sku": data.sku,
        "selling_price": data.selling_price,
    }
    pid = previews.create(
        org_id, "add_product", data.model_dump(), summary, AGENT.audit_actor
    )
    audit.log(
        org_id,
        "preview.add_product",
        AGENT.audit_actor,
        payload=summary,
        result={"preview_id": pid},
    )
    return {"preview_id": pid, "summary": summary}


@mcp.tool()
def create_import_invoice(
    org_id: str,
    items: list[dict[str, Any]],
    supplier_id: str | None = None,
    supplier_name: str | None = None,
    notes: str = "",
) -> dict[str, Any]:
    """Propose an import (stock purchase). `items` = [{sku, quantity, unit_price}].
    Returns preview_id + summary; call confirm_action(org_id, preview_id) to commit."""
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
    pid = previews.create(
        org_id, "create_import_invoice", data.model_dump(), summary, AGENT.audit_actor
    )
    audit.log(
        org_id,
        "preview.create_import_invoice",
        AGENT.audit_actor,
        payload=summary,
        result={"preview_id": pid},
    )
    return {"preview_id": pid, "summary": summary}


@mcp.tool()
def create_service_invoice(
    org_id: str,
    items: list[dict[str, Any]],
    customer_id: str | None = None,
    customer_name: str | None = None,
    notes: str = "",
) -> dict[str, Any]:
    """Propose a service/sales invoice. `items` = [{sku?, description?, quantity, unit_price}].
    Returns preview_id + summary; call confirm_action(org_id, preview_id) to commit."""
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
    pid = previews.create(
        org_id, "create_service_invoice", data.model_dump(), summary, AGENT.audit_actor
    )
    audit.log(
        org_id,
        "preview.create_service_invoice",
        AGENT.audit_actor,
        payload=summary,
        result={"preview_id": pid},
    )
    return {"preview_id": pid, "summary": summary}


@mcp.tool()
def confirm_action(org_id: str, preview_id: str) -> dict[str, Any]:
    """Commit a previously previewed destructive action."""
    action, payload = previews.consume(org_id, preview_id, AGENT.audit_actor)
    if action == "add_product":
        return inventory.create_product(org_id, ProductCreate(**payload), AGENT)
    if action == "create_import_invoice":
        parsed = ImportInvoiceCreate(**payload)
        return invoices.create_import_invoice(org_id, parsed, AGENT)
    if action == "create_service_invoice":
        parsed = ServiceInvoiceCreate(**payload)
        return invoices.create_service_invoice(org_id, parsed, AGENT)
    raise HTTPException(status.HTTP_400_BAD_REQUEST, f"unknown preview action: {action}")


# ── ASGI middleware: API key enforcement ────────────────────────────────

class ApiKeyMiddleware(BaseHTTPMiddleware):
    """Every /mcp/** request must authenticate as the agent. Accept either:
    - `X-API-Key: <key>`              (REST shim)
    - `Authorization: Bearer <key>`   (Claude Desktop / mcp-remote / Anthropic
                                       native MCP — the standard MCP auth)

    Constant-time compare avoids leaking key contents via timing.
    """

    async def dispatch(self, request: Request, call_next):  # type: ignore[no-untyped-def, override]
        import hmac

        expected = get_settings().openclaw_api_key
        presented = request.headers.get("x-api-key") or ""
        if not presented:
            auth = request.headers.get("authorization") or ""
            if auth.lower().startswith("bearer "):
                presented = auth.split(" ", 1)[1]
        if not presented or not hmac.compare_digest(presented, expected):
            return JSONResponse({"error": "invalid api key"}, status_code=401)
        return await call_next(request)


def mcp_asgi_app() -> ASGIApp:
    """Return the MCP Streamable-HTTP ASGI app, wrapped with API-key auth."""
    inner = mcp.streamable_http_app()
    return ApiKeyMiddleware(inner)  # type: ignore[return-value]
