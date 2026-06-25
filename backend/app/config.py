"""application settings, loaded from environment / .env.

all config is explicit and fail-loud: missing required secrets raise at startup rather
than producing mysterious runtime errors. no secret has a usable default.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import Field, PostgresDsn, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

Environment = Literal["development", "production"]
LLMProviderName = Literal["openrouter", "openai", "anthropic", "ollama"]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # core
    environment: Environment = "development"
    database_url: PostgresDsn
    log_level: str = "INFO"

    # secrets (no defaults on purpose)
    fernet_key: str
    session_secret: str

    # session
    session_ttl_days: int = 30

    # anilist oauth
    anilist_client_id: str
    anilist_client_secret: str
    anilist_redirect_uri: str
    anilist_auth_url: str = "https://anilist.co/api/v2/oauth/authorize"
    anilist_token_url: str = "https://anilist.co/api/v2/oauth/token"
    anilist_graphql_url: str = "https://graphql.anilist.co"

    # llm
    llm_provider: LLMProviderName = "openrouter"
    llm_api_key: str = ""
    llm_model: str = ""
    llm_extraction_model: str = ""
    ollama_base_url: str = "http://localhost:11434"

    # context / memory
    max_context_tokens: int = 8000
    history_message_limit: int = 20
    max_user_message_chars: int = 2000

    # sync
    sync_stale_seconds: int = 600

    # rate limiting (in-process token bucket; SINGLE-WORKER only, see
    # middleware/rate_limit.py). disable in tests that aren't exercising limits.
    rate_limit_enabled: bool = True
    rate_limit_auth_per_min: int = 10
    rate_limit_chat_per_min: int = 20
    rate_limit_sync_per_min: int = 1

    # frontend / cors
    frontend_origin: str = "http://localhost:3000"

    @field_validator("fernet_key", "session_secret")
    @classmethod
    def _non_empty_secret(cls, v: str, info) -> str:
        if not v or not v.strip():
            raise ValueError(f"{info.field_name} must be set (no empty secret allowed)")
        return v

    @property
    def cookie_secure(self) -> bool:
        # only send cookies over https in production; allow http on localhost dev
        return self.environment == "production"

    @property
    def database_url_str(self) -> str:
        return str(self.database_url)


@lru_cache
def get_settings() -> Settings:
    """cached settings accessor. raises on first call if required env is missing."""
    return Settings()  # type: ignore[call-arg]
