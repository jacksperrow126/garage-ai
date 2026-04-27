"""One-shot: register our /zalo/webhook URL with the Zalo Bot platform.

Usage:
    cd backend
    # Pull secrets from Secret Manager into env, or supply via .env
    export ZALO_BOT_TOKEN=$(gcloud secrets versions access latest \
        --secret=zalo-bot-token --project garage-manager-ai)
    export ZALO_WEBHOOK_SECRET=$(gcloud secrets versions access latest \
        --secret=zalo-webhook-secret --project garage-manager-ai)
    python scripts/setup_zalo_webhook.py

Defaults to the production Cloud Run URL. Override with WEBHOOK_URL env if
testing against a tunnel (ngrok / cloudflared)."""

from __future__ import annotations

import asyncio
import os
import sys

# Allow `python scripts/setup_zalo_webhook.py` to import app.* without
# installing the package.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.services.zalo_client import set_webhook

DEFAULT_URL = (
    "https://garage-ai-api-969667367100.asia-southeast1.run.app/zalo/webhook"
)


async def main() -> None:
    if not os.environ.get("ZALO_BOT_TOKEN"):
        sys.exit("ZALO_BOT_TOKEN not set")
    secret = os.environ.get("ZALO_WEBHOOK_SECRET")
    if not secret:
        sys.exit("ZALO_WEBHOOK_SECRET not set")

    url = os.environ.get("WEBHOOK_URL", DEFAULT_URL)
    print(f"Registering webhook: {url}")
    result = await set_webhook(url, secret)
    print(result)


if __name__ == "__main__":
    asyncio.run(main())
