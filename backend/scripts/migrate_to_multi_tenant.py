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

from app.auth import Principal
from app.firestore import get_db
from app.models.customer import CustomerCreate
from app.models.invoice import (
    ImportInvoiceCreate,
    ImportInvoiceItemIn,
    ServiceInvoiceCreate,
    ServiceInvoiceItemIn,
)
from app.models.product import ProductCreate
from app.models.supplier import SupplierCreate
from app.services import customers, inventory, invoices, orgs, suppliers, zalo_users

# Hard-coded — single-shop, single-admin scenario. The Zalo ID was captured
# from the first webhook trace; if it ever changes, edit here.
ADMIN_ZALO_ID = "8f705344d20d3b53621c"
ADMIN_NAME = "Owner"
FIRST_ORG_NAME = "Garage Test"

# Synthetic principal used by the seeder so audit logs cleanly attribute
# bootstrap rows to "user:bootstrap" instead of mixing them with real activity.
BOOTSTRAP = Principal(actor="user", uid="bootstrap", role="owner")

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

    Uses `list_documents()` instead of `stream()` so we also visit "phantom"
    parent docs — refs that exist only because they have subcollections
    underneath (e.g. `conversations/{zalo_id}` has no fields itself, only
    a `messages/` subcollection). `stream()` would skip those and we'd
    leave the subcollection orphaned.

    Returns the number of *actual* documents deleted (or that would be,
    on dry run). Phantom parents don't count toward that total."""
    deleted = 0
    for ref in col.list_documents(page_size=batch_size):
        for sub in ref.collections():
            deleted += _delete_collection_recursive(sub, batch_size, dry_run)
        # Only the docs that actually carry data count + are physically
        # deleted; phantom parents disappear automatically once their
        # subcollections are empty.
        snap = ref.get()
        if snap.exists:
            if not dry_run:
                ref.delete()
            deleted += 1
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


def bootstrap() -> str:
    """Create the admin Zalo user and the first org. Returns the new
    org_id so callers (e.g. the seeder) can scope test data correctly."""
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
    return org["id"]


def seed_test_data(org_id: str) -> None:
    """Populate the test org with realistic data running through the real
    service layer — every row goes through transactions, every change
    leaves an audit log, moving-average cost is computed honestly."""
    print(f"  seeding products + import invoice into /{org_id}/")
    # 1. Create the products (qty=0, just defines selling price + SKU)
    products_spec = [
        ("Dầu nhớt 5W-30", "DAUNHOT5W30", 200_000),
        ("Lọc gió", "LOCGIO", 120_000),
        ("Bugi NGK", "BUGI", 50_000),
        ("Lốp xe Michelin 185/65R15", "LOPXE", 1_500_000),
        ("Phanh dầu DOT 4", "PHANHDAU", 80_000),
    ]
    for name, sku, price in products_spec:
        inventory.create_product(
            org_id,
            ProductCreate(name=name, sku=sku, selling_price=price),
            BOOTSTRAP,
        )

    # 2. Supplier
    sup = suppliers.create(
        org_id,
        SupplierCreate(name="NCC Castrol", phone="0911111111"),
        BOOTSTRAP,
    )

    # 3. Import invoice — gives every product realistic quantity + avg_cost
    print("  seeding 1 import invoice (5 items)")
    invoices.create_import_invoice(
        org_id,
        ImportInvoiceCreate(
            supplier_id=sup["id"],
            supplier_name="NCC Castrol",
            items=[
                ImportInvoiceItemIn(sku="DAUNHOT5W30", quantity=10, unit_price=150_000),
                ImportInvoiceItemIn(sku="LOCGIO", quantity=8, unit_price=80_000),
                ImportInvoiceItemIn(sku="BUGI", quantity=20, unit_price=30_000),
                ImportInvoiceItemIn(sku="LOPXE", quantity=4, unit_price=1_200_000),
                ImportInvoiceItemIn(sku="PHANHDAU", quantity=6, unit_price=50_000),
            ],
            notes="Bootstrap test import",
        ),
        BOOTSTRAP,
    )

    # 4. Customers
    print("  seeding 3 customers")
    cust_tuan = customers.create(
        org_id, CustomerCreate(name="Anh Tuấn", phone="0901111111"), BOOTSTRAP
    )
    customers.create(
        org_id, CustomerCreate(name="Chị Mai", phone="0902222222"), BOOTSTRAP
    )
    customers.create(
        org_id, CustomerCreate(name="Anh Bình", phone="0903333333"), BOOTSTRAP
    )

    # 5. One service invoice (so reports have something to show)
    print("  seeding 1 service invoice (sale to anh Tuấn)")
    invoices.create_service_invoice(
        org_id,
        ServiceInvoiceCreate(
            customer_id=cust_tuan["id"],
            customer_name="Anh Tuấn",
            items=[
                ServiceInvoiceItemIn(sku="DAUNHOT5W30", quantity=1, unit_price=200_000),
                ServiceInvoiceItemIn(
                    description="Công thay dầu", quantity=1, unit_price=100_000
                ),
            ],
            notes="Bootstrap test sale",
        ),
        BOOTSTRAP,
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    grp = parser.add_mutually_exclusive_group(required=True)
    grp.add_argument("--dry-run", action="store_true", help="preview deletions, no writes")
    grp.add_argument("--yes", action="store_true", help="actually wipe + bootstrap")
    parser.add_argument(
        "--skip-seed",
        action="store_true",
        help="skip seeding test products / customers / invoices (use for the real shop later)",
    )
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
    org_id = bootstrap()
    print()

    if not args.skip_seed:
        print("== Step 4: seed test data ==")
        seed_test_data(org_id)
        print()

    print("Done. Now deploy the multi-tenant code.")


if __name__ == "__main__":
    main()
