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
    # Where browsers reach Supabase, for signed links to files. Defaults to `supabase_url`;
    # set it when the API reaches Supabase at a different address than the browser does.
    supabase_public_url: str | None = None
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

    # Alerts for the operator, emailed by the worker's sweep (D99). Without an address and an
    # SMTP host they are only logged, as in local development.
    alert_email: str | None = None
    smtp_host: str | None = None
    smtp_port: int = 587
    smtp_username: str = ""
    smtp_password: SecretStr = SecretStr("")
    # The sender; defaults to alert_email. Must be an address the SMTP service may send from.
    smtp_from: str | None = None
    # STARTTLS on a plain connection; port 465 always uses TLS from the start instead.
    smtp_starttls: bool = True
    # Estimated inference spend, in US dollars, above which an alert is sent once a day or
    # month. Expected spend is $20-25 a month (D90).
    alert_daily_spend_usd: float = 5.0
    alert_monthly_spend_usd: float = 30.0
    # A job still waiting this long means the worker isn't being woken.
    alert_job_wait_minutes: int = 60


@lru_cache
def get_settings() -> Settings:
    return Settings()
