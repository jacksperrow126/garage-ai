from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.auth import Principal, require_agent_or_user
from app.models.product import ProductCreate, ProductUpdate
from app.services import inventory

router = APIRouter(prefix="/products", tags=["products"])


@router.get("")
def list_products(
    query: str | None = Query(default=None),
    low_stock_only: bool = Query(default=False),
    _: Principal = Depends(require_agent_or_user),
) -> list[dict]:
    return inventory.list_products(query=query, low_stock_only=low_stock_only)


@router.get("/{sku}")
def get_product(sku: str, _: Principal = Depends(require_agent_or_user)) -> dict:
    product = inventory.get_product(sku.upper())
    if not product:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "product not found")
    return product


@router.post("", status_code=status.HTTP_201_CREATED)
def create_product(
    data: ProductCreate,
    principal: Principal = Depends(require_agent_or_user),
) -> dict:
    return inventory.create_product(data, principal)


@router.patch("/{sku}")
def update_product(
    sku: str,
    data: ProductUpdate,
    principal: Principal = Depends(require_agent_or_user),
) -> dict:
    return inventory.update_product(sku.upper(), data, principal)
