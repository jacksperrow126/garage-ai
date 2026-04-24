from datetime import datetime
from typing import Annotated

from pydantic import BaseModel, Field, StringConstraints

PhoneStr = Annotated[str, StringConstraints(strip_whitespace=True, max_length=20)]
Name120 = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=120)]


class SupplierCreate(BaseModel):
    name: Name120
    phone: PhoneStr = ""
    address: Annotated[str, StringConstraints(max_length=240)] = ""
    note: Annotated[str, StringConstraints(max_length=500)] = ""


class SupplierUpdate(BaseModel):
    name: Name120 | None = None
    phone: PhoneStr | None = None
    address: Annotated[str, StringConstraints(max_length=240)] | None = None
    note: Annotated[str, StringConstraints(max_length=500)] | None = None


class Supplier(BaseModel):
    id: str
    name: str
    phone: str = ""
    address: str = ""
    note: str = ""
    created_at: datetime
