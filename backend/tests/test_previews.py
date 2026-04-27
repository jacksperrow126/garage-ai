"""Two-phase confirmation: preview is single-use and actor-scoped."""

from __future__ import annotations

import pytest
from fastapi import HTTPException

from app.services import previews


def test_create_and_consume_preview(org_id: str) -> None:
    pid = previews.create(
        org_id,
        "add_product",
        {"name": "A", "sku": "A1", "selling_price": 10},
        {"what": "add_product"},
        "ai:openclaw",
    )
    assert isinstance(pid, str)
    action, payload = previews.consume(org_id, pid, "ai:openclaw")
    assert action == "add_product"
    assert payload["sku"] == "A1"


def test_preview_cannot_be_consumed_twice(org_id: str) -> None:
    pid = previews.create(
        org_id,
        "add_product",
        {"name": "A", "sku": "A1", "selling_price": 10},
        {"what": "add_product"},
        "ai:openclaw",
    )
    previews.consume(org_id, pid, "ai:openclaw")
    with pytest.raises(HTTPException) as excinfo:
        previews.consume(org_id, pid, "ai:openclaw")
    assert excinfo.value.status_code == 400


def test_preview_rejected_for_wrong_actor(org_id: str) -> None:
    pid = previews.create(
        org_id,
        "add_product",
        {"name": "A", "sku": "A1", "selling_price": 10},
        {"what": "add_product"},
        "ai:openclaw",
    )
    with pytest.raises(HTTPException) as excinfo:
        previews.consume(org_id, pid, "user:someoneelse")
    assert excinfo.value.status_code == 403
