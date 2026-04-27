"""One-shot: wipe legacy single-tenant data, bootstrap multi-tenant scaffolding.

After this runs, the only data remaining in Firestore is:
  - zalo_users/{ADMIN_ZALO_ID} with system_role=admin
  - organizations/{first_org_id}
  - organizations/{first_org_id}/members/{ADMIN_ZALO_ID} with role=owner

The legacy top-level collections (products, invoices, customers, suppliers,
adjustments, stock_moves, audit_logs, previews, conversations,
zalo_messages_seen) are deleted recursively.

Usage:
    cd backend
    export GOOGLE_CLOUD_PROJECT=garage-manager-ai
    export GOOGLE_APPLICATION_CREDENTIALS=...   # or use ADC
    export OPENCLAW_API_KEY=$(gcloud secrets versions access latest \
        --secret=openclaw-api-key --project=garage-manager-ai)

    # Dry-run first to confirm what gets deleted:
    python scripts/migrate_to_multi_tenant.py --dry-run

    # When ready:
    python scripts/migrate_to_multi_tenant.py --yes

This runs **locally** with prod credentials before deploying the new
multi-tenant code. After this completes, deploy the rest of the
multi-tenant change set.
"""

from __future__ import annotations

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from google.cloud import firestore

from app.firestore import get_db
from app.services import orgs, zalo_users

# Hard-coded — single-shop, single-admin scenario. The Zalo ID was captured
# from the first webhook trace; if it ever changes, edit here.
ADMIN_ZALO_ID = "8f705344d20d3b53621c"
ADMIN_NAME = "Owner"
FIRST_ORG_NAME = "Garage Chính"

LEGACY_COLLECTIONS = [
    "products",
    "invoices",
    "customers",
    "suppliers",
    "adjustments",
    "stock_moves",
    "audit_logs",
    "previews",
    "conversations",
    "zalo_messages_seen",
]


def _delete_collection_recursive(
    col: firestore.CollectionReference, batch_size: int = 200, dry_run: bool = True
) -> int:
    """Recursively delete every doc in `col`, descending into any subcollections.

    Returns the number of documents deleted (or that would be, on dry run)."""
    deleted = 0
    while True:
        docs = list(col.limit(batch_size).stream())
        if not docs:
            break
        for snap in docs:
            ref = snap.reference
            for sub in ref.collections():
                deleted += _delete_collection_recursive(sub, batch_size, dry_run)
            if not dry_run:
                ref.delete()
            deleted += 1
        if len(docs) < batch_size:
            break
    return deleted


def wipe_legacy(dry_run: bool) -> None:
    db = get_db()
    total = 0
    for name in LEGACY_COLLECTIONS:
        col = db.collection(name)
        count = _delete_collection_recursive(col, dry_run=dry_run)
        verb = "would delete" if dry_run else "deleted"
        print(f"  {verb} {count:>5} docs from /{name}")
        total += count
    print(f"  ── total: {total} docs ──")


def wipe_existing_orgs(dry_run: bool) -> None:
    """If a prior partial migration left orgs/zalo_users behind, clear them
    so this run produces deterministic state."""
    db = get_db()
    for name in ("organizations", "zalo_users"):
        col = db.collection(name)
        count = _delete_collection_recursive(col, dry_run=dry_run)
        verb = "would delete" if dry_run else "deleted"
        print(f"  {verb} {count:>5} docs from /{name}")


def bootstrap() -> None:
    """Create the admin Zalo user and the first org. Idempotent in the
    sense that orgs.create_org generates a fresh slug if "garage-chinh"
    already exists — but we wiped above, so fresh creation is expected."""
    print(f"  creating zalo_users/{ADMIN_ZALO_ID} as admin")
    zalo_users.upsert(
        ADMIN_ZALO_ID,
        name=ADMIN_NAME,
        system_role="admin",
        added_by="bootstrap",
    )

    print(f"  creating organization {FIRST_ORG_NAME!r}")
    org = orgs.create_org(name=FIRST_ORG_NAME, owner_zalo_id=ADMIN_ZALO_ID)
    print(f"    slug: {org['id']}")

    print(f"  setting primary_org_id={org['id']} on admin")
    zalo_users.set_primary_org(ADMIN_ZALO_ID, org["id"])


def main() -> None:
    parser = argparse.ArgumentParser()
    grp = parser.add_mutually_exclusive_group(required=True)
    grp.add_argument("--dry-run", action="store_true", help="preview deletions, no writes")
    grp.add_argument("--yes", action="store_true", help="actually wipe + bootstrap")
    args = parser.parse_args()

    project = os.environ.get("GOOGLE_CLOUD_PROJECT", "(unset)")
    print(f"Project: {project}")
    print(f"Admin Zalo ID: {ADMIN_ZALO_ID}")
    print(f"First org: {FIRST_ORG_NAME!r}")
    print()

    print("== Step 1: wipe legacy collections ==")
    wipe_legacy(dry_run=args.dry_run)
    print()

    print("== Step 2: wipe any prior orgs / zalo_users ==")
    wipe_existing_orgs(dry_run=args.dry_run)
    print()

    if args.dry_run:
        print("Dry run complete. Re-run with --yes to actually wipe + bootstrap.")
        return

    print("== Step 3: bootstrap admin + first org ==")
    bootstrap()
    print()
    print("Done. Now deploy the multi-tenant code.")


if __name__ == "__main__":
    main()
