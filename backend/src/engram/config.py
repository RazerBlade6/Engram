from functools import lru_cache

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime configuration, read from environment variables prefixed with ENGRAM_."""

    model_config = SettingsConfigDict(
        env_prefix="ENGRAM_", env_file=("../.env", ".env"), extra="ignore"
    )

    environment: str = "development"
    # Defaults match `supabase start`.
    database_url: str = "postgresql://postgres:postgres@127.0.0.1:54322/postgres"
    supabase_url: str = "http://127.0.0.1:54321"
    # The `iss` claim in access tokens. Defaults to `<supabase_url>/auth/v1`; set it when the
    # API reaches Supabase at a different address than the browser does (as in Docker).
    supabase_jwt_issuer: str | None = None
    supabase_secret_key: SecretStr = SecretStr("")
    web_url: str = "http://localhost:3000"
    cors_origins: list[str] = ["http://localhost:3000"]
    worker_poll_interval_seconds: float = 2.0

    # Model per job, as `provider:model`. Provisional until the eval suite decides (D25);
    # card generation stays on the stronger model until it passes the card-quality eval (D26).
    model_figure_description: str = "anthropic:claude-haiku-5-5"
    model_card_generation: str = "anthropic:claude-opus-5-5"
    model_chat: str = "anthropic:claude-opus-5-5"
    model_grading: str = "anthropic:claude-opus-5-5"

    # Local embedding model (ONNX, in-process). Its dimension is fixed in the schema.
    embedding_model: str = "BAAI/bge-small-en-v1.5"


@lru_cache
def get_settings() -> Settings:
    return Settings()
