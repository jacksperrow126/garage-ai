from typing import Any

from google.cloud import firestore

from app.firestore import get_db, server_timestamp


def log(
    action: str,
    actor: str,
    *,
    payload: dict[str, Any] | None = None,
    result: dict[str, Any] | None = None,
    tx: firestore.Transaction | None = None,
) -> None:
    """Append an immutable audit entry.

    If called inside a transaction, the write is staged on that transaction.
    Otherwise we write immediately with the batching client.
    """
    db = get_db()
    ref = db.collection("audit_logs").document()
    data = {
        "actor": actor,
        "action": action,
        "payload": payload or {},
        "result": result or {},
        "created_at": server_timestamp(),
    }
    if tx is not None:
        tx.set(ref, data)
    else:
        ref.set(data)
