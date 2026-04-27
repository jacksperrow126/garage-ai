# garage-ai

A garage management platform for a small car service shop in Vietnam.
Brother-in-law runs the shop through Zalo chat (via an in-house Claude
agent); owner monitors via a bilingual (VI/EN) web admin panel.

## Architecture

```
[Brother-in-law] ──Zalo Bot──▶ [/zalo/webhook] ──▶ [Claude Haiku 4.5 (Anthropic)]
                                                          │ MCP connector
                                                          ▼
                                              [/mcp/ on same FastAPI] ──▶ [Firestore]
                                                          ▲
[Owner (browser)] ──▶ [Next.js / Firebase App Hosting] ───┘
                       (same-origin rewrites to the API)
```

- **Backend** (`backend/`) — FastAPI on Cloud Run. Exposes `/api/v1/*`
  (REST), `/mcp/` (MCP Streamable HTTP), and `/zalo/webhook` (Zalo Bot
  inbound). Single `services/` layer is the source of truth for all
  surfaces. Firestore transactions enforce moving-average cost, invoice
  immutability, and atomic stock updates.
- **Frontend** (`frontend/`) — Next.js 15 App Router, Tailwind v4, bilingual
  (Vietnamese default, English toggle). Deployed to Firebase App Hosting,
  auto-building on push to `master`.
- **Data** (`firestore.rules`, `firestore.indexes.json`) — Firestore in
  native mode. Security rules deny all direct client access; all reads/writes
  go through our backend.
- **AI** — Anthropic Claude Haiku 4.5 via the Messages API's native MCP
  connector. We invoke Claude from the Zalo webhook handler; Claude calls
  back into our `/mcp/` to use shop tools. System prompt in
  [`backend/app/services/AGENT_PROMPT.md`](backend/app/services/AGENT_PROMPT.md)
  (lives next to `agent.py` so it ships with the Docker image).

## Features

### Inventory
- Products keyed by SKU (unique, stable, uppercased)
- Quantity + selling price + **moving-average cost** + last import price
- Low-stock warnings (threshold configurable in backend `config.py`)

### Invoices
- Two types: **import** (stock purchase) and **service** (sale / repair)
- Service invoices mix product lines (inventory-backed) and labor lines
- `cost_price` is snapshotted at sale time against current avg cost
- Write-once — edits go through `adjustments/` documents, never mutate the
  original invoice
- Every invoice creation runs as a single Firestore transaction: stock,
  avg-cost, invoice doc, stock-move audit, and audit-log all atomic

### AI / MCP
- Claude (via Anthropic Messages API + native MCP connector) calls tools
  over `/mcp/` with `Authorization: Bearer <API_KEY>`. The same key is also
  accepted as `X-API-Key` for direct REST callers.
- Destructive tools (`create_import_invoice`, `create_service_invoice`,
  `add_product`) use two-phase confirmation — first call returns a
  `preview_id`, second call (`confirm_action`) commits
- Vietnamese queries answered: "còn bao nhiêu X?", "nhập thêm 5 X giá Y",
  "hôm nay lời bao nhiêu?", "tháng này doanh thu?", "dịch vụ nào lời nhất?"

### Admin panel
- Dashboard (today revenue/cost/profit, low-stock, recent invoices)
- Inventory with search + add product
- Invoices list + create (import/service tabs) + detail
- Customers with search + history
- Suppliers CRUD
- Reports (monthly totals, top products)
- Mobile-friendly

## Quick start (local dev)

```bash
# 1. Clone
git clone git@personal:jacksperrow126/garage-ai.git
cd garage-ai

# 2. Backend
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -e '.[dev]'
cp .env.example .env           # fill in OPENCLAW_API_KEY

# 3. Firebase emulators (Firestore + Auth)
cd ..
firebase emulators:start --only firestore,auth
#   ─ this runs in one terminal

# 4. Run backend (in another terminal)
cd backend
source .venv/bin/activate
uvicorn app.main:app --reload --port 8000

# 5. Run frontend (in another terminal)
cd frontend
cp .env.local.example .env.local   # set NEXT_PUBLIC_API_URL=http://localhost:8000
npm install
npm run dev                         # http://localhost:3000

# 6. Run tests
cd backend
pytest                              # emulator must be up
```

## Deploy

See [`docs/DEPLOY.md`](docs/DEPLOY.md) for the full step-by-step.
Highlights:
- Backend → `gcloud run deploy` (Dockerfile-based), region `asia-southeast1`
- Firestore rules/indexes → `firebase deploy --only firestore`
- Frontend → connect GitHub repo to Firebase App Hosting; auto-deploys
  on push to `master`

## Repo layout

```
garage-ai/
├── backend/          # FastAPI + MCP + services + tests
├── frontend/         # Next.js admin panel
├── docs/             # DEPLOY.md, MULTI_TENANT.md
├── firebase.json
├── firestore.rules
├── firestore.indexes.json
├── .firebaserc
├── .gitignore
└── README.md
```

## Conventions

- **Currency**: all prices stored as integer VND. No fractional đồng, no
  multi-currency.
- **Timezones**: timestamps stored UTC; UI formats to `Asia/Ho_Chi_Minh`.
- **SKU normalization**: uppercased, whitespace-trimmed at the Pydantic
  validation layer. `oil 5w30` → `OIL5W30`.
- **Auth**: admin panel uses Firebase ID tokens; the agent uses a shared
  API key (stored in Secret Manager, rotated quarterly), accepted as either
  `X-API-Key` or `Authorization: Bearer`.
- **Immutability**: invoices can't be edited; use adjustments. This is
  enforced by the absence of a PATCH route — there is nothing to call.

## License

Private project. All rights reserved.
