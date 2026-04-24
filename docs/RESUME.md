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

**Secrets to keep in sync locally** (must match across `.env` files):

| Var                         | Where           | Value             |
|-----------------------------|-----------------|-------------------|
| `OPENCLAW_API_KEY`          | `backend/.env`  | `dev-secret-key`  |
| `NEXT_PUBLIC_API_KEY`       | `frontend/.env.local` | `dev-secret-key` |

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

## 5. ⚠️ Auth is currently dropped

Firebase Auth was removed from the frontend to unblock local dev. The
frontend sends `X-API-Key: dev-secret-key` directly to the backend (via
Next.js rewrite — same-origin, not cross-origin). This is NOT safe to
deploy — in production the key would be shipped to browsers.

### What was removed (commit 2025-04-24)
- `src/app/(auth)/login/page.tsx` — Google sign-in page
- `src/hooks/useAuth.ts` — auth state hook
- `src/lib/firebase.ts` — client Firebase SDK init
- Auth gate in `src/app/(app)/layout.tsx`
- Logout button in `src/components/Nav.tsx`

### What remains (still useful)
- Backend `require_user` and `require_agent_or_user` in `app/auth.py`
- Backend `/api/v1/me` endpoint
- `firebase` npm package still installed
- Firebase Auth emulator still runs

### Plan to re-enable

1. Reinstall login + auth:
   - `src/hooks/useAuth.ts` — subscribe to `onAuthStateChanged`
   - `src/lib/firebase.ts` — initialize app from `NEXT_PUBLIC_FIREBASE_*` vars
   - `src/app/(auth)/login/page.tsx` — Google sign-in (use emulator locally)
   - Restore logout button in `Nav.tsx`
2. Replace `X-API-Key` in `src/lib/api.ts` with `Authorization: Bearer <idToken>`
3. Drop `NEXT_PUBLIC_API_KEY` from `.env.local.example` + `.env.local`
4. Update `(app)/layout.tsx` to redirect to `/login` when not authenticated
5. Locally: connect to Auth emulator via
   `connectAuthEmulator(auth, "http://localhost:9099")` inside `firebase.ts`
6. Production: populate `NEXT_PUBLIC_FIREBASE_*` env vars from Firebase
   console → Project Settings → Web app

History preserved: the prior Firebase-integrated versions are in git at
`49b01d2` (initial commit).

## 6. Quick checks

| Check              | URL / command                                             |
|--------------------|-----------------------------------------------------------|
| Emulator UI        | http://127.0.0.1:4000                                     |
| Backend health     | `curl http://127.0.0.1:8000/api/v1/health`                |
| API (via rewrite)  | `curl http://127.0.0.1:3000/api/v1/products -H 'X-API-Key: dev-secret-key'` |
| Admin panel        | http://127.0.0.1:3000                                     |
| MCP endpoint       | `curl -I http://127.0.0.1:8000/mcp/ -H 'X-API-Key: dev-secret-key'` |
| Backend tests      | `pytest` inside `backend/` with emulator env vars         |
