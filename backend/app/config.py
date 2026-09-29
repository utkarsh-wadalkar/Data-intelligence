from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(
            Path(__file__).resolve().parents[2] / ".env",
            Path(__file__).resolve().parents[1] / ".env",
        ),
        extra="ignore",
    )

    database_url: str = "sqlite:///./data-intelligence.db"
    clerk_jwks_url: str = ""
    clerk_issuer: str = ""
    clerk_organization_id: str = ""
    openrouter_api_key: str = ""
    firecrawl_api_key: str = ""
    ollama_base_url: str = "http://localhost:11434"
    model_provider: str = "openrouter"
    allow_paid_providers: bool = False
    dispatch_mode: str = "local"
    modal_app_name: str = "data-intelligence"
    frontend_origin: str = "http://localhost:3000"


@lru_cache
def settings() -> Settings:
    return Settings()
