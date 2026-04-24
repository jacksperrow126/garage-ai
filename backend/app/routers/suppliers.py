from fastapi import APIRouter, Depends, HTTPException, status

from app.auth import Principal, require_agent_or_user
from app.models.supplier import SupplierCreate, SupplierUpdate
from app.services import suppliers

router = APIRouter(prefix="/suppliers", tags=["suppliers"])


@router.get("")
def list_suppliers(_: Principal = Depends(require_agent_or_user)) -> list[dict]:
    return suppliers.list_all()


@router.get("/{supplier_id}")
def get_supplier(supplier_id: str, _: Principal = Depends(require_agent_or_user)) -> dict:
    s = suppliers.get(supplier_id)
    if not s:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "supplier not found")
    return s


@router.post("", status_code=status.HTTP_201_CREATED)
def create_supplier(
    data: SupplierCreate,
    principal: Principal = Depends(require_agent_or_user),
) -> dict:
    return suppliers.create(data, principal)


@router.patch("/{supplier_id}")
def update_supplier(
    supplier_id: str,
    data: SupplierUpdate,
    principal: Principal = Depends(require_agent_or_user),
) -> dict:
    return suppliers.update(supplier_id, data, principal)


@router.delete("/{supplier_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_supplier(
    supplier_id: str,
    principal: Principal = Depends(require_agent_or_user),
) -> None:
    suppliers.delete(supplier_id, principal)
