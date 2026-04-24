"""Reporting queries. All reports filter by Asia/Ho_Chi_Minh calendar days /
months, even though timestamps are stored in UTC. The conversion happens at
query-boundary time using zoneinfo."""

from __future__ import annotations

from datetime import date, datetime, time, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from google.cloud import firestore

from app.firestore import get_db

VN_TZ = ZoneInfo("Asia/Ho_Chi_Minh")


def _day_range_utc(d: date) -> tuple[datetime, datetime]:
    start_local = datetime.combine(d, time.min, tzinfo=VN_TZ)
    end_local = start_local + timedelta(days=1)
    return start_local, end_local


def _month_range_utc(year: int, month: int) -> tuple[datetime, datetime]:
    start_local = datetime(year, month, 1, tzinfo=VN_TZ)
    if month == 12:
        end_local = datetime(year + 1, 1, 1, tzinfo=VN_TZ)
    else:
        end_local = datetime(year, month + 1, 1, tzinfo=VN_TZ)
    return start_local, end_local


def _service_invoices_in(start: datetime, end: datetime) -> list[dict[str, Any]]:
    col = get_db().collection("invoices")
    q = (
        col.where("type", "==", "service")
        .where("status", "==", "posted")
        .where("created_at", ">=", start)
        .where("created_at", "<", end)
    )
    return [{"id": doc.id, **(doc.to_dict() or {})} for doc in q.stream()]


def daily(d: date | None = None) -> dict[str, Any]:
    if d is None:
        d = datetime.now(VN_TZ).date()
    start, end = _day_range_utc(d)
    invoices = _service_invoices_in(start, end)
    revenue = sum(int(inv.get("total_revenue") or 0) for inv in invoices)
    cost = sum(int(inv.get("total_cost") or 0) for inv in invoices)
    return {
        "date": d.isoformat(),
        "invoice_count": len(invoices),
        "total_revenue": revenue,
        "total_cost": cost,
        "profit": revenue - cost,
    }


def monthly(year: int, month: int) -> dict[str, Any]:
    start, end = _month_range_utc(year, month)
    invoices = _service_invoices_in(start, end)
    revenue = sum(int(inv.get("total_revenue") or 0) for inv in invoices)
    cost = sum(int(inv.get("total_cost") or 0) for inv in invoices)
    return {
        "year": year,
        "month": month,
        "invoice_count": len(invoices),
        "total_revenue": revenue,
        "total_cost": cost,
        "profit": revenue - cost,
    }


def top_products(
    period: str = "month", limit: int = 10
) -> list[dict[str, Any]]:
    """Top products by profit contribution over the given period.
    period ∈ {"day", "week", "month"}."""
    now = datetime.now(VN_TZ)
    today = now.date()
    if period == "day":
        start, end = _day_range_utc(today)
    elif period == "week":
        start, end = _day_range_utc(today - timedelta(days=today.weekday()))
        end = start + timedelta(days=7)
    else:
        start, end = _month_range_utc(today.year, today.month)

    invoices = _service_invoices_in(start, end)
    by_sku: dict[str, dict[str, Any]] = {}
    for inv in invoices:
        for item in inv.get("items") or []:
            sku = item.get("sku")
            if not sku:
                continue
            row = by_sku.setdefault(
                sku,
                {
                    "sku": sku,
                    "description": item.get("description", sku),
                    "quantity": 0,
                    "revenue": 0,
                    "cost": 0,
                    "profit": 0,
                },
            )
            row["quantity"] += int(item.get("quantity", 0))
            row["revenue"] += int(item.get("line_total_revenue", 0))
            row["cost"] += int(item.get("line_total_cost", 0))
            row["profit"] = row["revenue"] - row["cost"]

    return sorted(by_sku.values(), key=lambda r: r["profit"], reverse=True)[:limit]


def revenue_summary(from_date: date, to_date: date) -> dict[str, Any]:
    start, _ = _day_range_utc(from_date)
    _, end = _day_range_utc(to_date)
    invoices = _service_invoices_in(start, end)
    revenue = sum(int(inv.get("total_revenue") or 0) for inv in invoices)
    cost = sum(int(inv.get("total_cost") or 0) for inv in invoices)
    return {
        "from": from_date.isoformat(),
        "to": to_date.isoformat(),
        "invoice_count": len(invoices),
        "total_revenue": revenue,
        "total_cost": cost,
        "profit": revenue - cost,
    }
