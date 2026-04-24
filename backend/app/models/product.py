from datetime import datetime
from typing import Annotated

from pydantic import BaseModel, Field, StringConstraints


# VND is stored as integers — no fractions of a đồng
VndInt = Annotated[int, Field(ge=0, le=10**12)]
Sku = Annotated[str, StringConstraints(strip_whitespace=True, to_upper=True, min_length=1, max_length=40)]


class ProductCreate(BaseModel):
    name: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=120)]
    sku: Sku | None = None
    selling_price: VndInt


class ProductUpdate(BaseModel):
    """PATCH payload — intentionally omits quantity, average_cost, last_import_price.
    Those can only change via invoice creation (transactional)."""

    name: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=120)] | None = None
    selling_price: VndInt | None = None
    active: bool | None = None


class Product(BaseModel):
    id: str
    name: str
    sku: Sku
    quantity: int = Field(ge=0)
    selling_price: VndInt
    average_cost: VndInt
    last_import_price: VndInt
    active: bool = True
    created_at: datetime
    updated_at: datetime
