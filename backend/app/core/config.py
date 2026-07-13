from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict
from dotenv import dotenv_values
config = dotenv_values(".env")
assert config["OPENAI_API_KEY"] is not None, "Please Enter an API Key"

class Settings(BaseSettings):
    app_name: str = "ScholarRAG"
    openai_api_key: str = config["OPENAI_API_KEY"]
    openai_model: str = "gpt-4o"
    openai_embed_model: str = "text-embedding-3-small"
    chroma_persist_dir: Path = Path("backend/data/chroma")
    upload_dir: Path = Path("backend/data/uploads")
    collection_name: str = "textbooks"
    cors_origins: list[str] = ["http://localhost:8501", "http://127.0.0.1:8501"]
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")
    backend_url: str = "http://localhost:8000"


settings = Settings()

settings.chroma_persist_dir.mkdir(parents=True, exist_ok=True)
settings.upload_dir.mkdir(parents=True, exist_ok=True)
