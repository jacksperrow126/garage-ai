# Deployment guide

Deploy targets:
- **Backend** (FastAPI + MCP) → Cloud Run, region `asia-southeast1`
- **Frontend** (Next.js) → Firebase App Hosting
- **Data** → Firestore (native mode)
- **Auth** → Firebase Auth
- **Secrets** → Google Secret Manager

## 0. Prerequisites

```bash
# macOS
brew install firebase-cli google-cloud-sdk
gcloud init            # log in, pick / create a project
firebase login         # same account as above
```

You'll need billing enabled on the GCP project for Cloud Run + Firestore.

## 1. Create the Firebase project

```bash
firebase projects:create garage-ai-prod          # IDs are globally unique
firebase use --add                                # alias → default
```

Then in the Firebase console:
- **Build → Firestore Database** → Create in native mode, region `asia-southeast1`
- **Build → Authentication** → Enable **Email/Password** and **Google** providers
- **Build → App Hosting** → we'll wire this up in step 4

## 2. Deploy Firestore rules + indexes

```bash
firebase deploy --only firestore:rules,firestore:indexes
```

Rules deny all direct client access — the backend Admin SDK bypasses them, so
Firestore is reachable only via our FastAPI service. Indexes match the plan.

## 3. Deploy the backend to Cloud Run

### 3a. Create the OpenClaw API key secret

```bash
echo -n "$(openssl rand -hex 32)" | \
    gcloud secrets create openclaw-api-key --data-file=-
```

Keep this secret — OpenClaw will need it as `X-API-Key` on every MCP/REST call.

### 3b. Deploy

```bash
cd backend
gcloud run deploy garage-api \
    --source . \
    --region asia-southeast1 \
    --platform managed \
    --allow-unauthenticated \
    --set-env-vars "APP_ENV=prod,GOOGLE_CLOUD_PROJECT=garage-ai-prod,ADMIN_ORIGINS=https://garage-ai-admin--garage-ai-prod.us-central1.hosted.app" \
    --set-secrets "OPENCLAW_API_KEY=openclaw-api-key:latest"
```

The `--source .` flag uses Cloud Build with the Dockerfile. First build is
~3 min; subsequent builds are faster due to layer caching.

Note the service URL in the output — it looks like
`https://garage-api-<hash>-as.a.run.app`.

### 3c. Grant Firestore access

Cloud Run's default service account needs `roles/datastore.user`:

```bash
PROJECT=garage-ai-prod
SA="$(gcloud iam service-accounts list \
      --filter='name:compute' --format='value(email)' --project=$PROJECT)"
gcloud projects add-iam-policy-binding $PROJECT \
    --member="serviceAccount:$SA" \
    --role="roles/datastore.user"
```

## 4. Deploy the frontend to App Hosting

### 4a. Connect the GitHub repo

In the Firebase console → **Build → App Hosting → Get started**:
- Connect GitHub, authorize the Firebase GitHub app for
  `jacksperrow126/garage-ai`
- **Root directory**: `frontend`
- **Backend name**: `garage-ai-admin` (must match `firebase.json`)
- **Branch**: `master`
- **Region**: `asia-east1` (closest to Vietnam currently supported)

### 4b. Set env vars

In **App Hosting → garage-ai-admin → Environment**:

| Var                                 | Source        | Value                                         |
|-------------------------------------|---------------|-----------------------------------------------|
| `NEXT_PUBLIC_API_URL`               | plain text    | the Cloud Run URL from step 3b                |
| `NEXT_PUBLIC_FIREBASE_PROJECT_ID`   | plain text    | `garage-ai-prod`                              |
| `NEXT_PUBLIC_FIREBASE_API_KEY`      | Secret Mgr    | copy from Firebase console → Project Settings |
| `NEXT_PUBLIC_FIREBASE_AUTH_DOMAIN`  | plain text    | `garage-ai-prod.firebaseapp.com`              |
| `NEXT_PUBLIC_FIREBASE_APP_ID`       | plain text    | from Project Settings                         |

`apphosting.yaml` in the repo pins runtime limits (min=0, max=3 instances).

### 4c. First deploy

Push to `master`:

```bash
git push origin master
```

App Hosting builds Next.js and rolls out the first release. Watch progress
in the Firebase console.

## 5. Assign roles

Grant yourself owner role via the Admin SDK script:

```bash
cd backend
export GOOGLE_APPLICATION_CREDENTIALS=./service-account.json
python scripts/set_role.py --email you@example.com --role owner --project garage-ai-prod
```

Sign out / sign in in the admin panel for the claim to take effect.

## 6. Wire up OpenClaw

In OpenClaw's UI, add a new **MCP server**:
- **URL**: `https://garage-api-<hash>-as.a.run.app/mcp`
- **Auth**: API key header `X-API-Key: <secret from step 3a>`

Paste the Vietnamese system prompt from [OPENCLAW_PROMPT.md](OPENCLAW_PROMPT.md)
into OpenClaw's agent configuration.

## 7. Verify end-to-end

Follow the smoke test in the main `README.md`. At a minimum:
- Sign in to the admin panel, see an empty dashboard
- Create a product via UI
- Import stock via Zalo → OpenClaw → MCP → confirm → verify in inventory
- "Hôm nay lời bao nhiêu?" in Zalo returns the correct profit

## Launch checklist

- [ ] Firestore **backups** enabled (console → Firestore → Backups)
- [ ] Cloud Run **min-instances = 0**, max = 3
- [ ] Budget alert at $20/month on the GCP project
- [ ] Owner has Firebase console access; brother-in-law does not
- [ ] `OPENCLAW_API_KEY` rotated (and updated in OpenClaw) at least quarterly
- [ ] README runbook known to one other person

## Emergency runbook

- **Admin panel down**: check App Hosting → Rollouts. Roll back to last green.
- **Cloud Run 503**: check Cloud Run → garage-api → Logs. Usually Firestore
  creds or missing IAM. Re-run step 3c.
- **OpenClaw 401 from MCP**: rotate `OPENCLAW_API_KEY`; update secret in
  Cloud Run and in OpenClaw simultaneously.
- **"Invoice created twice"**: impossible — invoice creation is transactional;
  check audit_logs for the actual action sequence.
