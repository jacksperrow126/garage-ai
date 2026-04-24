"""HTTP-level invariants: invoices cannot be PATCHed; /me requires auth."""

from __future__ import annotations

import os

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client() -> TestClient:
    os.environ["OPENCLAW_API_KEY"] = "test-key"
    from app.main import create_app

    return TestClient(create_app())


def test_invoice_patch_is_not_allowed(client: TestClient) -> None:
    # PATCH /api/v1/invoices/{id} route does not exist → 405 Method Not Allowed
    r = client.patch("/api/v1/invoices/anything", headers={"X-API-Key": "test-key"}, json={})
    assert r.status_code == 405


def test_health_is_public(client: TestClient) -> None:
    r = client.get("/api/v1/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_me_requires_token(client: TestClient) -> None:
    r = client.get("/api/v1/me")
    assert r.status_code == 401


def test_mcp_requires_api_key(client: TestClient) -> None:
    r = client.get("/mcp/")
    assert r.status_code == 401
