# Resuming local dev

Everything you need to bring the system back up after a laptop restart or a
fresh Claude session. Assumes the repo is already cloned at
`/Users/annguyen/Documents/garage-ai/` and deps are installed.

## 1. Fresh install (once per machine)

```bash
cd /Users/annguyen/Documents/garage-ai

# backend
cd backend
python3 -m venv .venv && source .venv/bin/activate
python -m pip install -e '.[dev]'
cp .env.example .env          # already has OPENCLAW_API_KEY=change-me-locally
cd ..

# frontend
cd frontend
npm install
cp .env.local.example .env.local
cd ..
```

**Secrets / env to keep in sync locally:**

| Var                                       | Where                  | Value                       |
|-------------------------------------------|------------------------|-----------------------------|
| `OPENCLAW_API_KEY`                        | `backend/.env`         | `dev-secret-key` (MCP only) |
| `NEXT_PUBLIC_FIREBASE_PROJECT_ID`         | `frontend/.env.local`  | `garage-ai-test`            |
| `NEXT_PUBLIC_FIREBASE_AUTH_EMULATOR_HOST` | `frontend/.env.local`  | `localhost:9099`            |

The frontend authenticates to the backend with Firebase ID tokens —
`OPENCLAW_API_KEY` is only used by the MCP server (OpenClaw agent).

## 2. Start everything (three terminals)

### Terminal 1 — Firebase emulators

```bash
cd /Users/annguyen/Documents/garage-ai
npx firebase-tools@latest emulators:start --only firestore,auth --project garage-ai-test
```

Wait for "All emulators ready!" — Firestore on `:8080`, Auth on `:9099`, UI
on http://127.0.0.1:4000.

### Terminal 2 — Backend (FastAPI)

```bash
cd /Users/annguyen/Documents/garage-ai/backend
source .venv/bin/activate
FIRESTORE_EMULATOR_HOST=localhost:8080 \
FIREBASE_AUTH_EMULATOR_HOST=localhost:9099 \
GOOGLE_CLOUD_PROJECT=garage-ai-test \
OPENCLAW_API_KEY=dev-secret-key \
APP_ENV=local \
ADMIN_ORIGINS=http://localhost:3000 \
uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
```

`GET http://127.0.0.1:8000/api/v1/health` → `{"status":"ok"}`.
OpenAPI UI → http://127.0.0.1:8000/api/docs.

### Terminal 3 — Frontend (Next.js)

```bash
cd /Users/annguyen/Documents/garage-ai/frontend
npm run dev
```

Admin panel → http://127.0.0.1:3000.

## 3. Run backend tests

```bash
cd backend && source .venv/bin/activate
FIRESTORE_EMULATOR_HOST=localhost:8080 \
FIREBASE_AUTH_EMULATOR_HOST=localhost:9099 \
GOOGLE_CLOUD_PROJECT=garage-ai-test \
OPENCLAW_API_KEY=test-key \
python -m pytest
```

Expected: **12 tests pass** (inventory math, invoice atomicity, immutability,
preview/confirm, MCP auth guard).

## 4. Smoke test the flow end-to-end

These curls seed data through the **agent path** (`X-API-Key`). The browser
path uses Firebase ID tokens — see §5.

```bash
# Create a product
curl -X POST http://127.0.0.1:8000/api/v1/products \
  -H 'X-API-Key: dev-secret-key' -H 'Content-Type: application/json' \
  -d '{"name":"Engine oil 5W-30","sku":"OIL5W30","selling_price":200000}'

# Import 10 @ 150k
curl -X POST http://127.0.0.1:8000/api/v1/invoices \
  -H 'X-API-Key: dev-secret-key' -H 'Content-Type: application/json' \
  -d '{"type":"import","items":[{"sku":"OIL5W30","quantity":10,"unit_price":150000}]}'

# Dashboard should now show this product; inventory page at http://127.0.0.1:3000/inventory
```

## 5. Auth

Firebase Auth is wired up end-to-end. The frontend fetches an ID token via
the Firebase SDK and sends `Authorization: Bearer <token>` to the backend;
`require_user` / `require_agent_or_user` in `app/auth.py` verify with the
Admin SDK.

### Local sign-in flow (with Auth emulator)

The Next.js app auto-connects to the Auth emulator when
`NEXT_PUBLIC_FIREBASE_AUTH_EMULATOR_HOST=localhost:9099` is set (default in
`.env.local.example`).

1. Visit http://localhost:3000 → redirected to `/login`.
2. Click "Sign in with Google". The emulator pops up a fake-Google dialog;
   pick "Add new account", enter any email, and submit. The user is created
   in the emulator.
3. You land on `/` but API calls will 403 until the user has a role claim
   (see below).

### Grant an owner / manager role

The backend reads `role` from the token's custom claims (defaults to
`manager` if missing — see `app/auth.py:41`). To promote yourself to
`owner` against the emulator:

```bash
cd backend && source .venv/bin/activate
FIREBASE_AUTH_EMULATOR_HOST=localhost:9099 \
GOOGLE_CLOUD_PROJECT=garage-ai-test \
python scripts/set_role.py --email you@example.com --role owner --project garage-ai-test
```

Then sign out and back in so the new token carries the updated claim.

### Production rollout checklist

- Populate `NEXT_PUBLIC_FIREBASE_API_KEY`, `NEXT_PUBLIC_FIREBASE_AUTH_DOMAIN`,
  `NEXT_PUBLIC_FIREBASE_PROJECT_ID`, `NEXT_PUBLIC_FIREBASE_APP_ID` on
  Firebase App Hosting (console → App Hosting → Environment). Leave
  `NEXT_PUBLIC_FIREBASE_AUTH_EMULATOR_HOST` **unset**.
- In Firebase console → Authentication → Sign-in method, enable Google and
  add the owner's email to the allowed list (or rely on role-claims alone).
- Run `scripts/set_role.py` once against the real project (with
  `GOOGLE_APPLICATION_CREDENTIALS` pointing at a service account) to grant
  the owner role to the real account.

## 6. Quick checks

| Check              | URL / command                                             |
|--------------------|-----------------------------------------------------------|
| Emulator UI        | http://127.0.0.1:4000                                     |
| Backend health     | `curl http://127.0.0.1:8000/api/v1/health`                |
| API (via rewrite)  | `curl http://127.0.0.1:3000/api/v1/products -H 'X-API-Key: dev-secret-key'` |
| Admin panel        | http://127.0.0.1:3000                                     |
| MCP endpoint       | `curl -I http://127.0.0.1:8000/mcp/ -H 'X-API-Key: dev-secret-key'` |
| Backend tests      | `pytest` inside `backend/` with emulator env vars         |
