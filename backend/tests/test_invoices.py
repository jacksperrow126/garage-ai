"""Core correctness tests: moving-average cost, stock atomicity, immutability."""

from __future__ import annotations

import pytest
from fastapi import HTTPException

from app.auth import Principal
from app.models.invoice import (
    ImportInvoiceCreate,
    ImportInvoiceItemIn,
    ServiceInvoiceCreate,
    ServiceInvoiceItemIn,
)
from app.models.product import ProductCreate
from app.services import inventory, invoices


def _seed_product(owner: Principal, *, sku: str = "OIL5W30", price: int = 200_000) -> None:
    inventory.create_product(
        ProductCreate(name="Engine oil 5W-30", sku=sku, selling_price=price),
        owner,
    )


def test_avg_cost_after_three_imports(owner: Principal) -> None:
    _seed_product(owner)
    # 10 @ 150k
    invoices.create_import_invoice(
        ImportInvoiceCreate(items=[ImportInvoiceItemIn(sku="OIL5W30", quantity=10, unit_price=150_000)]),
        owner,
    )
    p = inventory.get_product("OIL5W30")
    assert p and p["quantity"] == 10 and p["average_cost"] == 150_000

    # 10 @ 170k  →  (10*150k + 10*170k) / 20 = 160k
    invoices.create_import_invoice(
        ImportInvoiceCreate(items=[ImportInvoiceItemIn(sku="OIL5W30", quantity=10, unit_price=170_000)]),
        owner,
    )
    p = inventory.get_product("OIL5W30")
    assert p and p["quantity"] == 20 and p["average_cost"] == 160_000

    # 5 @ 180k  →  (20*160k + 5*180k) / 25 = 164k
    invoices.create_import_invoice(
        ImportInvoiceCreate(items=[ImportInvoiceItemIn(sku="OIL5W30", quantity=5, unit_price=180_000)]),
        owner,
    )
    p = inventory.get_product("OIL5W30")
    assert p and p["quantity"] == 25 and p["average_cost"] == 164_000


def test_service_invoice_decrements_stock_and_computes_profit(owner: Principal) -> None:
    _seed_product(owner)
    # Stock: 20 units with avg cost = 160k after two imports
    invoices.create_import_invoice(
        ImportInvoiceCreate(items=[ImportInvoiceItemIn(sku="OIL5W30", quantity=10, unit_price=150_000)]),
        owner,
    )
    invoices.create_import_invoice(
        ImportInvoiceCreate(items=[ImportInvoiceItemIn(sku="OIL5W30", quantity=10, unit_price=170_000)]),
        owner,
    )
    # Sell 1 OIL5W30 @ 200k, plus labor 100k
    inv = invoices.create_service_invoice(
        ServiceInvoiceCreate(
            customer_name="walk-in",
            items=[
                ServiceInvoiceItemIn(sku="OIL5W30", quantity=1, unit_price=200_000),
                ServiceInvoiceItemIn(description="Oil change labor", quantity=1, unit_price=100_000),
            ],
        ),
        owner,
    )
    assert inv["total_revenue"] == 300_000
    assert inv["total_cost"] == 160_000
    assert inv["profit"] == 140_000

    p = inventory.get_product("OIL5W30")
    assert p and p["quantity"] == 19


def test_oversell_is_rejected_atomically(owner: Principal) -> None:
    _seed_product(owner)
    invoices.create_import_invoice(
        ImportInvoiceCreate(items=[ImportInvoiceItemIn(sku="OIL5W30", quantity=5, unit_price=150_000)]),
        owner,
    )
    with pytest.raises(HTTPException) as excinfo:
        invoices.create_service_invoice(
            ServiceInvoiceCreate(
                items=[ServiceInvoiceItemIn(sku="OIL5W30", quantity=10, unit_price=200_000)],
            ),
            owner,
        )
    assert excinfo.value.status_code == 400
    # Stock unchanged
    p = inventory.get_product("OIL5W30")
    assert p and p["quantity"] == 5


def test_import_invoice_has_null_profit(owner: Principal) -> None:
    _seed_product(owner)
    inv = invoices.create_import_invoice(
        ImportInvoiceCreate(items=[ImportInvoiceItemIn(sku="OIL5W30", quantity=3, unit_price=150_000)]),
        owner,
    )
    assert inv["profit"] is None
    assert inv["total_cost"] == 450_000


def test_unknown_sku_rejected(owner: Principal) -> None:
    with pytest.raises(HTTPException) as excinfo:
        invoices.create_import_invoice(
            ImportInvoiceCreate(items=[ImportInvoiceItemIn(sku="NOPE", quantity=1, unit_price=1)]),
            owner,
        )
    assert excinfo.value.status_code == 404
