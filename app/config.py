from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "WhatsApp Agent Core"
    database_path: Path = Path("data/agent.db")
    openai_api_key: str | None = None
    openai_model: str = "gpt-4.1-mini"
    max_crawl_pages: int = 25
    max_page_bytes: int = 1_000_000
    request_timeout_seconds: float = 10

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


@lru_cache
def get_settings() -> Settings:
    return Settings()
