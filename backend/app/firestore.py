from functools import lru_cache

import firebase_admin
from firebase_admin import credentials
from google.cloud import firestore

from app.config import get_settings


@lru_cache
def get_firebase_app() -> firebase_admin.App:
    """Initialize firebase-admin once per process.

    On Cloud Run we rely on Application Default Credentials (the service
    account attached to the Cloud Run service). Locally, point
    GOOGLE_APPLICATION_CREDENTIALS at a service account JSON, or use the
    emulators (FIRESTORE_EMULATOR_HOST + FIREBASE_AUTH_EMULATOR_HOST).
    """
    settings = get_settings()
    if firebase_admin._apps:
        return firebase_admin.get_app()
    return firebase_admin.initialize_app(
        credentials.ApplicationDefault(),
        {"projectId": settings.google_cloud_project},
    )


@lru_cache
def get_db() -> firestore.Client:
    get_firebase_app()
    return firestore.Client(project=get_settings().google_cloud_project)


def server_timestamp() -> object:
    """Sentinel for Firestore SERVER_TIMESTAMP. Opaque by design."""
    return firestore.SERVER_TIMESTAMP
