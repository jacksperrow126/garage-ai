"""Pytest fixtures wiring tests to the Firestore emulator.

Prerequisites:
  - firebase-tools CLI installed
  - `firebase emulators:start --only firestore` running on localhost:8080
  - env vars: FIRESTORE_EMULATOR_HOST=localhost:8080, GOOGLE_CLOUD_PROJECT=garage-ai-test

If the emulator isn't up, tests are skipped (not failed) so `pytest` stays
usable in the absence of the emulator — e.g. on CI matrixes that handle
Firestore separately."""

from __future__ import annotations

import os
import socket
from collections.abc import Generator

import pytest

from app.auth import Principal

EMULATOR_HOST = os.environ.get("FIRESTORE_EMULATOR_HOST", "localhost:8080")


def _emulator_up(host_port: str) -> bool:
    host, port = host_port.split(":")
    try:
        with socket.create_connection((host, int(port)), timeout=0.5):
            return True
    except OSError:
        return False


# Seed required env vars BEFORE app.config gets imported anywhere.
os.environ.setdefault("FIRESTORE_EMULATOR_HOST", EMULATOR_HOST)
os.environ.setdefault("FIREBASE_AUTH_EMULATOR_HOST", "localhost:9099")
os.environ.setdefault("GOOGLE_CLOUD_PROJECT", "garage-ai-test")
os.environ.setdefault("OPENCLAW_API_KEY", "test-key")
os.environ.setdefault("APP_ENV", "local")


def pytest_collection_modifyitems(config, items):  # type: ignore[no-untyped-def]
    if _emulator_up(EMULATOR_HOST):
        return
    skip_marker = pytest.mark.skip(
        reason=f"Firestore emulator not reachable at {EMULATOR_HOST} "
        "— run `firebase emulators:start --only firestore`"
    )
    for item in items:
        item.add_marker(skip_marker)


@pytest.fixture
def owner() -> Principal:
    return Principal(actor="user", uid="test-owner", role="owner", email="owner@test")


@pytest.fixture
def agent() -> Principal:
    return Principal(actor="agent", uid="openclaw", role="manager")


@pytest.fixture
def org_id() -> str:
    """All multi-tenant tests run inside this fake org. Firestore lazily
    creates the parent doc when subcollection writes happen, so no explicit
    bootstrap is needed for read/write paths to work."""
    return "test-org"


@pytest.fixture(autouse=True)
def _reset_firestore() -> Generator[None, None, None]:
    """Wipe the emulator before every test via its REST admin endpoint."""
    import urllib.request

    project = os.environ["GOOGLE_CLOUD_PROJECT"]
    url = (
        f"http://{EMULATOR_HOST}/emulator/v1/projects/{project}/databases/"
        "(default)/documents"
    )
    req = urllib.request.Request(url, method="DELETE")
    try:
        urllib.request.urlopen(req, timeout=2)  # noqa: S310
    except Exception:  # noqa: BLE001 — emulator not up, tests already skipped
        pass
    yield
