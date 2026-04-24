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


def test_mcp_accepts_bearer_api_key(client: TestClient) -> None:
    """Claude Desktop via mcp-remote + Anthropic native MCP both send the
    key as Authorization: Bearer. Must pass the MCP middleware, not 401."""
    r = client.get("/mcp/", headers={"Authorization": "Bearer test-key"})
    # A 200/400/405/406 all mean auth passed and MCP itself answered.
    # The exact code depends on Streamable HTTP protocol negotiation on a
    # GET; anything other than 401 proves the auth layer let us through.
    assert r.status_code != 401


def test_bearer_api_key_accepted_on_agent_routes(client: TestClient) -> None:
    """OpenClaw / Anthropic Messages API-native MCP want Authorization:
    Bearer <api-key>. That must auth the same as X-API-Key."""
    r1 = client.get("/api/v1/products", headers={"X-API-Key": "test-key"})
    r2 = client.get("/api/v1/products", headers={"Authorization": "Bearer test-key"})
    assert r1.status_code == r2.status_code == 200


def test_bearer_wrong_key_rejected(client: TestClient) -> None:
    r = client.get("/api/v1/products", headers={"Authorization": "Bearer not-the-key"})
    assert r.status_code == 401
