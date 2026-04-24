from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.auth import Principal, require_agent_or_user
from app.models.customer import CustomerCreate, CustomerUpdate
from app.services import customers

router = APIRouter(prefix="/customers", tags=["customers"])


@router.get("")
def list_customers(
    query: str | None = Query(default=None),
    _: Principal = Depends(require_agent_or_user),
) -> list[dict]:
    if query:
        return customers.search(query)
    return customers.list_all()


@router.get("/{customer_id}")
def get_customer(customer_id: str, _: Principal = Depends(require_agent_or_user)) -> dict:
    c = customers.get(customer_id)
    if not c:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "customer not found")
    return c


@router.post("", status_code=status.HTTP_201_CREATED)
def create_customer(
    data: CustomerCreate,
    principal: Principal = Depends(require_agent_or_user),
) -> dict:
    return customers.create(data, principal)


@router.patch("/{customer_id}")
def update_customer(
    customer_id: str,
    data: CustomerUpdate,
    principal: Principal = Depends(require_agent_or_user),
) -> dict:
    return customers.update(customer_id, data, principal)


@router.delete("/{customer_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_customer(
    customer_id: str,
    principal: Principal = Depends(require_agent_or_user),
) -> None:
    customers.delete(customer_id, principal)


@router.get("/{customer_id}/history")
def customer_history(
    customer_id: str,
    _: Principal = Depends(require_agent_or_user),
) -> list[dict]:
    return customers.history(customer_id)
