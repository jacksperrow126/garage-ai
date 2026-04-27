from functools import lru_cache
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_env: Literal["local", "staging", "prod"] = "local"
    google_cloud_project: str = "garage-manager-ai"

    # Comma-separated origins; parsed into a list on access
    admin_origins: str = "http://localhost:3000"

    # Default org_id for REST routes when X-Org-ID header is absent.
    # Currently the test org used during multi-tenant rollout; will flip
    # to the real shop's slug when one is created via the bot.
    default_org_id: str = "garage-test"

    # Agent authentication — same key used for X-API-Key on REST and Bearer
    # on /mcp/. Name kept for backwards compat with existing Cloud Run env.
    openclaw_api_key: str

    # Preview TTL for two-phase confirmation of destructive MCP tools
    preview_ttl_seconds: int = 300

    # Low-stock threshold (units) — products below this show up as warnings
    low_stock_threshold: int = 3

    # ── Anthropic agent (Zalo bot brain) ───────────────────────────────
    anthropic_api_key: str = ""
    agent_model: str = "claude-haiku-4-5"
    # Where Claude's native MCP connector should call back into us.
    # Defaults to the deployed Cloud Run URL; override locally if needed.
    mcp_self_url: str = (
        "https://garage-ai-api-969667367100.asia-southeast1.run.app/mcp/"
    )

    # ── Zalo Bot ────────────────────────────────────────────────────────
    # Token from "Zalo Bot Manager" OA (format: "12345689:abc-xyz").
    zalo_bot_token: str = ""
    # Random secret we generate and pass to setWebhook; Zalo sends it back
    # on every webhook in X-Bot-Api-Secret-Token.
    zalo_webhook_secret: str = ""

    @property
    def admin_origin_list(self) -> list[str]:
        return [o.strip() for o in self.admin_origins.split(",") if o.strip()]

    @property
    def is_local(self) -> bool:
        return self.app_env == "local"


@lru_cache
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]
