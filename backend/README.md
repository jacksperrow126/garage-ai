# backend

FastAPI service that is simultaneously:
- the **REST API** for the Next.js admin panel (`/api/v1/*`, Firebase ID token)
- the **MCP server** for OpenClaw (`/mcp`, `X-API-Key`)

Both surfaces wrap the same `services/` layer. One set of invariants, two
delivery mechanisms.

## Layout

```
app/
├── main.py               # create_app(), mounts /api and /mcp
├── config.py             # pydantic-settings
├── auth.py               # Firebase token + API-key dependencies
├── firestore.py          # admin app + client factory
├── models/               # Pydantic schemas (in + out)
├── services/             # business logic — single source of truth
│   ├── audit.py          # immutable audit log
│   ├── inventory.py      # product CRUD, manual correction
│   ├── invoices.py       # import/service creation (transactional)
│   ├── invoice_read.py   # read-side queries (split from writes)
│   ├── reports.py        # daily/monthly/top-products
│   ├── previews.py       # two-phase confirmation store
│   ├── customers.py
│   └── suppliers.py
├── routers/              # HTTP shells over services/
└── mcp_server.py         # MCP tool registrations (also over services/)

tests/                    # pytest + Firestore emulator
scripts/set_role.py       # set Firebase Auth custom claims (role)
Dockerfile                # Cloud Run-ready
pyproject.toml
```

## Run

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e '.[dev]'

# In another terminal:
firebase emulators:start --only firestore,auth

# Back here:
export FIRESTORE_EMULATOR_HOST=localhost:8080
export FIREBASE_AUTH_EMULATOR_HOST=localhost:9099
export GOOGLE_CLOUD_PROJECT=garage-ai
export OPENCLAW_API_KEY=dev-secret
uvicorn app.main:app --reload --port 8000

# OpenAPI docs at http://localhost:8000/api/docs (dev only)
```

## Test

```bash
# Emulator must be running; tests auto-skip if not
pytest
```

Critical invariants tested:
- moving-avg cost after 3 imports matches the weighted-average formula
- concurrent imports of the same SKU don't drift (Firestore transaction
  retry under contention)
- service invoices atomically decrement stock and snapshot cost_price
- overselling raises 400 and writes nothing
- import invoices have `profit = null`
- `PATCH /api/v1/invoices/{id}` returns 405 (route doesn't exist by design)
- MCP endpoints require `X-API-Key`

## Design notes

### Products keyed by SKU
Firestore transactions are awkward with queries, so products' document ID
**is** the SKU. Lookups are O(1) direct reads. SKU is normalized (uppercase,
trimmed) at Pydantic validation time. SKUs are immutable — to rename, create
a new product and mark the old inactive.

### Moving-average cost
On import:
```
new_avg = (old_qty * old_avg + delta_qty * delta_unit_price) // new_qty
```
Integer division loses at most 1 VND per import — tracked in
`stock_moves` via `avg_cost_before`/`avg_cost_after` for audit. Tests
assert drift stays at 0 for the common cases.

### Two-phase confirmation
Destructive MCP tools stash a preview in `previews/` and return a
`preview_id` without writing. OpenClaw reads the summary back to the user
in Zalo. Only when `confirm_action(preview_id)` is called do we commit.
Previews expire after 5 minutes and are actor-scoped — a preview created
by one actor cannot be consumed by another.

### Invoice immutability
No PATCH endpoint on invoices. Changes go through `adjustments/`, which
record the reason + type (void/amend). The original invoice is marked
`status = "adjusted"` but its fields are never overwritten. For real
corrections (physical recount, return), the operator creates an inverse
invoice — this keeps the audit trail perfectly clean.

### Audit logging
Every state-changing call — human or AI — writes an `audit_logs/` entry.
In a transaction, the audit write is staged with the other writes so the
log never diverges from reality.
