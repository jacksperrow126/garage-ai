from datetime import date
from typing import Literal

from fastapi import APIRouter, Depends, Query

from app.auth import Principal, require_agent_or_user
from app.services import reports

router = APIRouter(prefix="/reports", tags=["reports"])


@router.get("/daily")
def daily(
    date_: date | None = Query(default=None, alias="date"),
    _: Principal = Depends(require_agent_or_user),
) -> dict:
    return reports.daily(date_)


@router.get("/monthly")
def monthly(
    year: int = Query(ge=2020, le=2100),
    month: int = Query(ge=1, le=12),
    _: Principal = Depends(require_agent_or_user),
) -> dict:
    return reports.monthly(year, month)


@router.get("/top-products")
def top_products(
    period: Literal["day", "week", "month"] = Query(default="month"),
    limit: int = Query(default=10, ge=1, le=50),
    _: Principal = Depends(require_agent_or_user),
) -> list[dict]:
    return reports.top_products(period, limit)


@router.get("/revenue-summary")
def revenue_summary(
    from_: date = Query(alias="from"),
    to: date = Query(),
    _: Principal = Depends(require_agent_or_user),
) -> dict:
    return reports.revenue_summary(from_, to)
