from functools import lru_cache
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_env: Literal["local", "staging", "prod"] = "local"
    google_cloud_project: str = "garage-manager-ai"

    # Comma-separated origins; parsed into a list on access
    admin_origins: str = "http://localhost:3000"

    # OpenClaw / agent authentication
    openclaw_api_key: str

    # Preview TTL for two-phase confirmation of destructive MCP tools
    preview_ttl_seconds: int = 300

    # Low-stock threshold (units) — products below this show up as warnings
    low_stock_threshold: int = 3

    @property
    def admin_origin_list(self) -> list[str]:
        return [o.strip() for o in self.admin_origins.split(",") if o.strip()]

    @property
    def is_local(self) -> bool:
        return self.app_env == "local"


@lru_cache
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]
