from typing import Any

from google.cloud import firestore

from app.firestore import org_collection, server_timestamp


def log(
    org_id: str,
    action: str,
    actor: str,
    *,
    payload: dict[str, Any] | None = None,
    result: dict[str, Any] | None = None,
    tx: firestore.Transaction | None = None,
) -> None:
    """Append an immutable audit entry under organizations/{org_id}/audit_logs.

    If called inside a transaction, the write is staged on that transaction.
    Otherwise we write immediately with the batching client.
    """
    ref = org_collection(org_id, "audit_logs").document()
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
