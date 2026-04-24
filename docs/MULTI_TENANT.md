# Multi-tenant plan

**Status:** NOT needed yet. Designed for eventual expansion from one garage
to many. Do this when the second real garage is lined up — not before.

## Current single-tenant reality

- Top-level collections (`/products`, `/invoices`, `/customers`,
  `/suppliers`, `/adjustments`, `/stock_moves`, `/audit_logs`) are global.
- Product document ID = SKU, globally unique within the project. Two
  garages cannot both have a `OIL5W30`.
- `OPENCLAW_API_KEY` is one shared secret; every OpenClaw agent uses it.
- `Principal.role` is `owner | manager`; doesn't encode garage membership.
- Firestore rules deny all direct client access; the backend Admin SDK
  bypasses them. No rule path enforces "user X sees only garage X data"
  because we never needed it.

## Target shape (when we do this)

Nest everything under a garage scope:

```
/garages/{garageId}                       — garage metadata, owner_uid
/garages/{garageId}/products/{sku}
/garages/{garageId}/invoices/{invoiceId}
/garages/{garageId}/customers/{customerId}
/garages/{garageId}/suppliers/{supplierId}
/garages/{garageId}/adjustments/{id}
/garages/{garageId}/stock_moves/{id}
/garages/{garageId}/audit_logs/{id}

/users/{uid}                              — { garage_ids: [...], role: ... }
/api_keys/{hashOfKey}                     — { garage_id, created_at, label }
```

## Migration plan (sketch)

### Backend

1. Services take `garageId` as the first arg; all `_ref` helpers prefix with
   `get_db().collection("garages").document(garageId).collection(...)`.
   Mechanical search-and-replace on ~8 files.
2. `require_user` / `require_agent_or_user` decode `garageId` from the
   route (`/garages/{garageId}/products/...`) or from a user's token
   claims; 403 if the requesting principal can't act on that garage.
3. MCP server: API key lookup becomes `api_keys/<hash>` → yields
   `garage_id`, not a global `AGENT` principal.
4. Reports / daily / monthly queries: scope to the garage's subcollection
   or use collection-group queries with a `where("garage_id", "==", ...)`
   equality filter. Pick subcollection — it's cheaper and avoids a
   cross-tenant index.

### Data model

Each document inside a garage's subcollection can drop `garage_id` (the
path itself encodes it). If we use collection-group queries, keep a
denormalized `garage_id` field for the filter.

SKUs stay unique within a garage but no longer globally. Existing
doc-ID convention works without change inside the subcollection.

### Firestore rules

Replace the blanket deny with an authenticated-read/write rule scoped by
claim:

```
match /garages/{garageId}/{document=**} {
  allow read, write: if request.auth != null
    && request.auth.token.role in ['owner', 'manager']
    && garageId in request.auth.token.garage_ids;
}
```

This still keeps the backend as the primary write path; the rule is
defense-in-depth if a client ever talks to Firestore directly.

### Indexes

Each composite index we have today (invoices, stock_moves, adjustments)
needs to be re-declared as a *collection group* index on the nested
collection. `firestore.indexes.json` with `"queryScope": "COLLECTION_GROUP"`.

### Auth claims

After user authenticates, backend `set_custom_user_claims` writes
`{ "role": "...", "garage_ids": ["g-abc"] }`. Frontend reads
`garageId` from URL or a state store. Backend validates on every call.

### One-time data migration

- Freeze writes for ~2 minutes.
- Create `garages/g-legacy` with current shop info.
- For each top-level collection, copy docs under
  `garages/g-legacy/{collection}/{id}` (Firestore Python client can batch).
- Flip the backend to the new shape; deploy.
- Sanity-check: every report still matches pre-migration.
- Delete top-level collections after ~a week if nothing went wrong.

Script belongs at `backend/scripts/migrate_to_multi_tenant.py` when the
time comes.

## What to do now (cheap, useful later)

1. **Service signatures stay SKU-agnostic and thin.** Today
   `_product_ref(sku)` is called from 4 places. When multi-tenant lands,
   it becomes `_product_ref(garage_id, sku)` — a mechanical refactor,
   not a redesign.
2. **Never embed literal project IDs in business logic.** Already good —
   all config goes through `Settings` / env.
3. **Audit-log `actor` field.** Currently `user:uid` / `ai:openclaw`.
   When multi-tenant lands, extend to `user:uid@garageId` without
   breaking consumers.
4. **Don't add features that assume "the" garage.** E.g., a "total
   inventory across shops" view would need rethinking. Avoid that framing.

## Rough size

- 2–3 engineer-days of code changes.
- 1 day for migration + verification.
- ~5 minutes of write-freeze during the flip.

Revisit this doc when the second garage is lined up.
