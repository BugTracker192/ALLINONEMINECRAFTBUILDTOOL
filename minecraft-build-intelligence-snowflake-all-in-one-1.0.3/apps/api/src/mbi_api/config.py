from __future__ import annotations

import hashlib
from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="MBI_", env_file=".env", extra="ignore")

    env: str = "development"
    database_url: str = "sqlite:///./var/mbi.db"
    redis_url: str = "redis://localhost:6379/0"
    object_store_root: Path = Path("var")
    asset_pack_path: Path | None = None
    max_upload_bytes: int = 512 * 1024 * 1024
    demo_inline_jobs: bool = True
    cors_origins: str = "http://localhost:5173"
    api_keys: str = ""
    rate_limit_requests: int = 240
    rate_limit_window_seconds: int = 60
    max_query_blocks: int = 250_000
    openai_base_url: str = "https://api.openai.com"
    anthropic_base_url: str = "https://api.anthropic.com"
    local_ai_base_url: str = "http://localhost:11434"
    ai_timeout_seconds: float = 120.0
    ai_max_iterations: int = 12
    ai_max_context_tokens: int = 64_000
    ai_max_output_tokens: int = 8_192
    renderer_service_url: str = "http://localhost:8090"
    renderer_timeout_seconds: float = 180.0
    artifact_signing_secret: str = ""
    artifact_url_ttl_seconds: int = 900
    upload_retention_days: int = 7
    snapshot_retention_days: int = 30
    export_retention_days: int = 30
    job_retention_days: int = 14
    ai_run_retention_days: int = 30
    idempotency_retention_days: int = 7

    @property
    def api_key_hashes(self) -> set[str]:
        return {
            hashlib.sha256(item.strip().encode()).hexdigest()
            for item in self.api_keys.split(",")
            if item.strip()
        }


@lru_cache
def get_settings() -> Settings:
    return Settings()
