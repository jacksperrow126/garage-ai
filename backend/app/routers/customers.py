from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.auth import Principal, require_agent_or_user, require_org_id
from app.models.customer import CustomerCreate, CustomerUpdate
from app.services import customers

router = APIRouter(prefix="/customers", tags=["customers"])


@router.get("")
def list_customers(
    query: str | None = Query(default=None),
    _: Principal = Depends(require_agent_or_user),
    org_id: str = Depends(require_org_id),
) -> list[dict]:
    if query:
        return customers.search(org_id, query)
    return customers.list_all(org_id)


@router.get("/{customer_id}")
def get_customer(
    customer_id: str,
    _: Principal = Depends(require_agent_or_user),
    org_id: str = Depends(require_org_id),
) -> dict:
    c = customers.get(org_id, customer_id)
    if not c:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "customer not found")
    return c


@router.post("", status_code=status.HTTP_201_CREATED)
def create_customer(
    data: CustomerCreate,
    principal: Principal = Depends(require_agent_or_user),
    org_id: str = Depends(require_org_id),
) -> dict:
    return customers.create(org_id, data, principal)


@router.patch("/{customer_id}")
def update_customer(
    customer_id: str,
    data: CustomerUpdate,
    principal: Principal = Depends(require_agent_or_user),
    org_id: str = Depends(require_org_id),
) -> dict:
    return customers.update(org_id, customer_id, data, principal)


@router.delete("/{customer_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_customer(
    customer_id: str,
    principal: Principal = Depends(require_agent_or_user),
    org_id: str = Depends(require_org_id),
) -> None:
    customers.delete(org_id, customer_id, principal)


@router.get("/{customer_id}/history")
def customer_history(
    customer_id: str,
    _: Principal = Depends(require_agent_or_user),
    org_id: str = Depends(require_org_id),
) -> list[dict]:
    return customers.history(org_id, customer_id)
