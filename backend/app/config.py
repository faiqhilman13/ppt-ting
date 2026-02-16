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
    scratch_renderer_url: str = "http://localhost:3002"
    public_base_url: str = "http://localhost:8000"
    frontend_origin: str = "http://localhost:5173"

    default_llm_provider: str = "mock"
    openai_api_key: str | None = None
    openai_model: str = "gpt-5-mini"
    anthropic_api_key: str | None = None
    anthropic_model: str = "claude-sonnet-4-20250514"
    anthropic_max_tokens: int = 8192
    minimax_api_key: str | None = None
    minimax_model: str = "MiniMax-M2.5"
    minimax_max_tokens: int = 16384
    minimax_base_url: str = "https://api.minimax.io/anthropic"
    exa_api_key: str | None = None
    exa_search_url: str = "https://api.exa.ai/search"
    pptx_skill_root: str | None = None
    scratch_theme: str = "default"

    onlyoffice_document_server_url: str = "http://localhost:8080"
    log_level: str = "INFO"
    suppress_job_poll_access_logs: bool = True
    suppress_httpx_info_logs: bool = True
    verbose_ai_trace: bool = True
    log_preview_chars: int = 180
    persist_job_events: bool = True
    persist_tool_runs: bool = True
    default_agent_mode: str = "bounded"
    default_quality_profile: str = "balanced"
    max_plan_steps: int = 12
    max_tool_runtime_seconds: int = 45
    max_correction_passes_server: int = 2
    job_events_page_size: int = 400

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
