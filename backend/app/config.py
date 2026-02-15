from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_STORAGE_ROOT = PROJECT_ROOT / "storage"
DEFAULT_DB_PATH = DEFAULT_STORAGE_ROOT / "app.db"


class Settings(BaseSettings):
    app_name: str = "PowerPoint Agent API"
    api_prefix: str = "/api"

    storage_root: Path = DEFAULT_STORAGE_ROOT
    database_url: str = f"sqlite:///{DEFAULT_DB_PATH.as_posix()}"
    redis_url: str = "redis://localhost:6379/0"
    renderer_url: str = "http://localhost:3001"
    public_base_url: str = "http://localhost:8000"
    frontend_origin: str = "http://localhost:5173"

    default_llm_provider: str = "mock"
    openai_api_key: str | None = None
    anthropic_api_key: str | None = None

    onlyoffice_document_server_url: str = "http://localhost:8080"

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")


settings = Settings()

for folder in [
    settings.storage_root,
    settings.storage_root / "templates",
    settings.storage_root / "uploads",
    settings.storage_root / "outputs",
    settings.storage_root / "citations",
    settings.storage_root / "manifests",
]:
    folder.mkdir(parents=True, exist_ok=True)
