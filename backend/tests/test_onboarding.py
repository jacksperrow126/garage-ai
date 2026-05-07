"""Onboarding state machine + access-request integration tests."""

from __future__ import annotations

from app.firestore import get_db
from app.services import access_requests, onboarding, orgs, zalo_users


def _seed_admin(zalo_id: str = "admin-zalo") -> None:
    zalo_users.upsert(zalo_id, name="Admin", system_role="admin")


def _create_pending_request(zalo_id: str, name: str = "Anh Tu") -> str:
    request, _ = access_requests.create_or_get_pending(
        zalo_id, name, "Cho em xin quyền"
    )
    return request["id"]


def test_first_owner_in_fresh_org_starts_onboarding() -> None:
    """The classic case: admin creates 'Garage Anh Tư' fresh and approves
    a new owner into it. Owner should land in garage_profile step."""
    _seed_admin()
    org = orgs.create_org("Garage Anh Tư", owner_zalo_id="admin-zalo")
    request_id = _create_pending_request("requester-zalo")

    result = access_requests.approve(
        request_id, org["id"], role="owner", resolved_by_zalo_id="admin-zalo"
    )

    assert result["needs_onboarding"] is True
    user = zalo_users.get("requester-zalo")
    assert user is not None
    assert user["onboarding_step"] == onboarding.STEP_GARAGE_PROFILE


def test_already_setup_org_skips_onboarding() -> None:
    """Second owner joining an org that already has profile data set
    (someone configured it earlier) → skip straight to done."""
    _seed_admin()
    org = orgs.create_org("Garage Already Live", owner_zalo_id="admin-zalo")
    # Simulate the org being set up.
    get_db().collection("organizations").document(org["id"]).update(
        {"address": "123 Some St", "phone": "0901234567"}
    )

    request_id = _create_pending_request("second-owner")
    result = access_requests.approve(
        request_id, org["id"], role="owner", resolved_by_zalo_id="admin-zalo"
    )

    assert result["needs_onboarding"] is False
    user = zalo_users.get("second-owner")
    assert user is not None
    assert user["onboarding_step"] == onboarding.STEP_DONE


def test_manager_role_never_triggers_onboarding() -> None:
    """Only owners go through onboarding. Managers added to a fresh org
    skip — they're staff joining, not setting up."""
    _seed_admin()
    org = orgs.create_org("Fresh Org", owner_zalo_id="admin-zalo")
    request_id = _create_pending_request("staff-zalo")

    result = access_requests.approve(
        request_id, org["id"], role="manager", resolved_by_zalo_id="admin-zalo"
    )

    assert result["needs_onboarding"] is False
    user = zalo_users.get("staff-zalo")
    assert user["onboarding_step"] == onboarding.STEP_DONE


def test_set_onboarding_step_transitions() -> None:
    """Direct state advance via the helper — what the MCP tool wraps."""
    zalo_users.upsert("user-x", name="X")
    zalo_users.set_onboarding_step("user-x", onboarding.STEP_GARAGE_PROFILE)
    assert zalo_users.get("user-x")["onboarding_step"] == onboarding.STEP_GARAGE_PROFILE
    zalo_users.set_onboarding_step("user-x", onboarding.STEP_FIRST_INVENTORY)
    assert (
        zalo_users.get("user-x")["onboarding_step"] == onboarding.STEP_FIRST_INVENTORY
    )
    zalo_users.set_onboarding_step("user-x", onboarding.STEP_DONE)
    assert zalo_users.get("user-x")["onboarding_step"] == onboarding.STEP_DONE


def test_is_org_already_setup_detects_profile_fields() -> None:
    _seed_admin()
    org = orgs.create_org("Empty Org", owner_zalo_id="admin-zalo")
    assert onboarding.is_org_already_setup(org["id"]) is False

    get_db().collection("organizations").document(org["id"]).update(
        {"address": "123"}
    )
    assert onboarding.is_org_already_setup(org["id"]) is True


def test_is_valid_step() -> None:
    assert onboarding.is_valid_step(None)
    assert onboarding.is_valid_step("garage_profile")
    assert onboarding.is_valid_step("first_inventory")
    assert onboarding.is_valid_step("done")
    assert not onboarding.is_valid_step("garbage")
    assert not onboarding.is_valid_step("")
