from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime configuration, read from environment variables prefixed with ENGRAM_."""

    model_config = SettingsConfigDict(env_prefix="ENGRAM_", env_file=".env", extra="ignore")

    environment: str = "development"
    database_url: str = "postgresql://engram:engram@localhost:5432/engram"
    cors_origins: list[str] = ["http://localhost:3000"]
    worker_poll_interval_seconds: float = 2.0


@lru_cache
def get_settings() -> Settings:
    return Settings()
