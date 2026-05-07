"""Unit tests for require_org_id's multi-tenant membership enforcement.

Calls the dep function directly with constructed Principals — no full
HTTP stack needed because the FastAPI Depends() metadata is ignored
when the function is invoked as a plain coroutine."""

from __future__ import annotations

import pytest
from fastapi import HTTPException

from app.auth import Principal, require_org_id
from app.config import Settings


def _settings(default_org: str = "garage-test") -> Settings:
    return Settings(
        openclaw_api_key="test-key",
        default_org_id=default_org,
        anthropic_api_key="x",
    )


def _user(
    primary_org_id: str | None = None, system_role: str | None = None
) -> Principal:
    return Principal(
        actor="user",
        uid="firebase-uid",
        role="owner",
        email="x@y",
        primary_org_id=primary_org_id,
        system_role=system_role,
    )


_AGENT = Principal(actor="agent", uid="openclaw", role="manager")


@pytest.mark.asyncio
async def test_agent_can_request_any_org() -> None:
    result = await require_org_id(
        x_org_id="any-org", settings=_settings(), principal=_AGENT
    )
    assert result == "any-org"


@pytest.mark.asyncio
async def test_user_with_matching_primary_org_id_passes() -> None:
    user = _user(primary_org_id="garage-anh-tu")
    result = await require_org_id(
        x_org_id="garage-anh-tu", settings=_settings(), principal=user
    )
    assert result == "garage-anh-tu"


@pytest.mark.asyncio
async def test_user_requesting_other_org_is_403() -> None:
    user = _user(primary_org_id="garage-anh-tu")
    with pytest.raises(HTTPException) as exc:
        await require_org_id(
            x_org_id="garage-someone-else",
            settings=_settings(),
            principal=user,
        )
    assert exc.value.status_code == 403


@pytest.mark.asyncio
async def test_system_admin_bypasses_membership() -> None:
    """system_role=admin (set in zalo_users for global admins) can hit
    any org without per-org membership."""
    admin = _user(primary_org_id="garage-anh-tu", system_role="admin")
    result = await require_org_id(
        x_org_id="garage-someone-else",
        settings=_settings(),
        principal=admin,
    )
    assert result == "garage-someone-else"


@pytest.mark.asyncio
async def test_user_without_primary_org_id_can_only_hit_default() -> None:
    """Anonymous-dev / partially-onboarded users have no primary_org_id;
    they can still reach the default org (single-tenant fallback) but not
    arbitrary orgs."""
    user = _user(primary_org_id=None)
    # Default org → ok.
    assert (
        await require_org_id(
            x_org_id=None, settings=_settings("garage-test"), principal=user
        )
        == "garage-test"
    )
    # Non-default org → 403.
    with pytest.raises(HTTPException) as exc:
        await require_org_id(
            x_org_id="some-other-org",
            settings=_settings("garage-test"),
            principal=user,
        )
    assert exc.value.status_code == 403


@pytest.mark.asyncio
async def test_missing_header_falls_back_to_default() -> None:
    user = _user(primary_org_id="garage-test")
    result = await require_org_id(
        x_org_id=None, settings=_settings("garage-test"), principal=user
    )
    assert result == "garage-test"
