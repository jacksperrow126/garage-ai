from datetime import datetime
from typing import Annotated

from pydantic import BaseModel, Field, StringConstraints

Name120 = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=120)]
PhoneStr = Annotated[str, StringConstraints(strip_whitespace=True, max_length=20)]


class Vehicle(BaseModel):
    license_plate: Annotated[str, StringConstraints(strip_whitespace=True, to_upper=True, max_length=20)] = ""
    make: Annotated[str, StringConstraints(max_length=40)] = ""
    model: Annotated[str, StringConstraints(max_length=40)] = ""
    year: int | None = Field(default=None, ge=1950, le=2100)
    note: Annotated[str, StringConstraints(max_length=240)] = ""


class CustomerCreate(BaseModel):
    name: Name120
    phone: PhoneStr = ""
    vehicles: list[Vehicle] = []
    note: Annotated[str, StringConstraints(max_length=500)] = ""


class CustomerUpdate(BaseModel):
    name: Name120 | None = None
    phone: PhoneStr | None = None
    vehicles: list[Vehicle] | None = None
    note: Annotated[str, StringConstraints(max_length=500)] | None = None


class Customer(BaseModel):
    id: str
    name: str
    phone: str = ""
    vehicles: list[Vehicle] = []
    note: str = ""
    created_at: datetime
