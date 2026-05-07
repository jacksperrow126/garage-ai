"""End-to-end test for the Zalo-mediated login flow.

Mints a login token via the same path the bot uses, posts it to the
exchange endpoint, asserts a Firebase custom token comes back and that
custom claims (role + primary_org_id) get persisted on the user.

Requires the Firebase Auth emulator to be reachable at localhost:9099
(set via FIREBASE_AUTH_EMULATOR_HOST in conftest)."""

from __future__ import annotations

import socket

import pytest
from fastapi.testclient import TestClient
from firebase_admin import auth as fb_auth

from app.firestore import get_db, get_firebase_app
from app.main import app
from app.services.auth_tokens import mint_login_token

AUTH_EMULATOR = "localhost:9099"


def _auth_emulator_up() -> bool:
    try:
        with socket.create_connection(tuple(AUTH_EMULATOR.split(":")), timeout=0.5):
            return True
    except OSError:
        return False


pytestmark = pytest.mark.skipif(
    not _auth_emulator_up(),
    reason="Firebase Auth emulator not reachable at localhost:9099",
)


def _seed_zalo_user(zalo_id: str, primary_org_id: str | None = "test-org") -> None:
    payload = {"name": "Anh Tu", "added_by": "test-seed"}
    if primary_org_id:
        payload["primary_org_id"] = primary_org_id
    get_db().collection("zalo_users").document(zalo_id).set(payload)


def _delete_auth_user(uid: str) -> None:
    """Clean up between runs — emulator persists across tests otherwise."""
    get_firebase_app()
    try:
        fb_auth.delete_user(uid)
    except fb_auth.UserNotFoundError:
        pass


def test_exchange_with_valid_token_returns_custom_token() -> None:
    zalo_id = "test-zalo-roundtrip"
    _delete_auth_user(zalo_id)
    _seed_zalo_user(zalo_id)

    token, _ = mint_login_token(zalo_id, ttl_seconds=120)
    client = TestClient(app)
    res = client.post("/public/auth/exchange", json={"token": token})
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["uid"] == zalo_id
    assert body["role"] == "owner"  # has primary_org_id → owner
    assert body["primary_org_id"] == "test-org"
    assert body["name"] == "Anh Tu"
    # Custom token is a JWT — three base64url-encoded segments.
    assert body["custom_token"].count(".") == 2

    # Custom claims must be persisted on the Firebase user so they survive
    # ID-token refresh.
    user = fb_auth.get_user(zalo_id)
    assert user.custom_claims == {
        "role": "owner",
        "primary_org_id": "test-org",
        "zalo_name": "Anh Tu",
    }
    _delete_auth_user(zalo_id)


def test_exchange_with_invalid_token_forbidden() -> None:
    client = TestClient(app)
    res = client.post("/public/auth/exchange", json={"token": "garbage"})
    assert res.status_code == 403


def test_exchange_with_expired_token_forbidden() -> None:
    token, _ = mint_login_token("test-zalo-expired", ttl_seconds=-10)
    client = TestClient(app)
    res = client.post("/public/auth/exchange", json={"token": token})
    assert res.status_code == 403


def test_exchange_for_unknown_zalo_id_404() -> None:
    """Token is valid but no zalo_users record exists → reject."""
    token, _ = mint_login_token("nonexistent-zalo", ttl_seconds=120)
    client = TestClient(app)
    res = client.post("/public/auth/exchange", json={"token": token})
    assert res.status_code == 404
