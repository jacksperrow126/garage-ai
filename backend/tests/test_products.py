"""Product creation: explicit SKU, auto-derived SKU, and collision handling."""

from __future__ import annotations

import pytest
from fastapi import HTTPException

from app.auth import Principal
from app.models.product import ProductCreate
from app.services import inventory


def test_auto_sku_from_vietnamese_name(owner: Principal, org_id: str) -> None:
    p = inventory.create_product(
        org_id, ProductCreate(name="Dầu nhớt 5W-30", selling_price=200_000), owner
    )
    assert p["sku"] == "DAUNHOT5W30"
    assert p["id"] == "DAUNHOT5W30"


def test_auto_sku_suffixes_on_collision(owner: Principal, org_id: str) -> None:
    inventory.create_product(
        org_id, ProductCreate(name="Dầu nhớt", selling_price=100_000), owner
    )
    second = inventory.create_product(
        org_id, ProductCreate(name="Dầu nhớt", selling_price=120_000), owner
    )
    assert second["sku"] == "DAUNHOT-02"


def test_explicit_sku_still_wins(owner: Principal, org_id: str) -> None:
    p = inventory.create_product(
        org_id,
        ProductCreate(name="Engine oil", sku="OIL5W30", selling_price=200_000),
        owner,
    )
    assert p["sku"] == "OIL5W30"


def test_explicit_sku_collision_is_409(owner: Principal, org_id: str) -> None:
    inventory.create_product(
        org_id,
        ProductCreate(name="Engine oil", sku="OIL5W30", selling_price=200_000),
        owner,
    )
    with pytest.raises(HTTPException) as exc:
        inventory.create_product(
            org_id,
            ProductCreate(name="Another", sku="OIL5W30", selling_price=100_000),
            owner,
        )
    assert exc.value.status_code == 409
