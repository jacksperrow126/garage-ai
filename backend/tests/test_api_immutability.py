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


def test_mcp_middleware_accepts_bearer_api_key() -> None:
    """Claude Desktop via mcp-remote + Anthropic native MCP both send the
    key as Authorization: Bearer. The ApiKeyMiddleware must not 401 on
    those requests. Tested against a stub inner app so we don't depend
    on MCP's async lifespan init."""
    from starlette.applications import Starlette
    from starlette.responses import JSONResponse
    from starlette.routing import Route
    from fastapi.testclient import TestClient as StarletteClient

    async def ok(_req):
        return JSONResponse({"ok": True})

    os.environ["OPENCLAW_API_KEY"] = "test-key"
    from app.mcp_server import ApiKeyMiddleware

    # Clear settings cache so it re-reads OPENCLAW_API_KEY.
    from app.config import get_settings
    get_settings.cache_clear()

    inner = Starlette(routes=[Route("/probe", ok, methods=["GET"])])
    wrapped = ApiKeyMiddleware(inner)
    c = StarletteClient(wrapped)

    assert c.get("/probe").status_code == 401  # no auth at all
    assert c.get("/probe", headers={"X-API-Key": "test-key"}).status_code == 200
    assert c.get("/probe", headers={"Authorization": "Bearer test-key"}).status_code == 200
    assert c.get("/probe", headers={"Authorization": "Bearer wrong"}).status_code == 401


def test_bearer_api_key_accepted_on_agent_routes(client: TestClient) -> None:
    """OpenClaw / Anthropic Messages API-native MCP want Authorization:
    Bearer <api-key>. That must auth the same as X-API-Key."""
    r1 = client.get("/api/v1/products", headers={"X-API-Key": "test-key"})
    r2 = client.get("/api/v1/products", headers={"Authorization": "Bearer test-key"})
    assert r1.status_code == r2.status_code == 200


def test_bearer_wrong_key_rejected(client: TestClient) -> None:
    r = client.get("/api/v1/products", headers={"Authorization": "Bearer not-the-key"})
    assert r.status_code == 401
