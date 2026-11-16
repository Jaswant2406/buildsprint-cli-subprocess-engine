"""Application configuration via environment variables."""
from __future__ import annotations

from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings  # type: ignore[import-untyped]

_ROOT = Path(__file__).resolve().parent.parent.parent
_BACKEND = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    model_config = {
        "env_file": [str(_ROOT / ".env"), str(_BACKEND / ".env"), ".env"],
        "env_file_encoding": "utf-8",
        "extra": "ignore",
    }

    # App
    app_env: str = Field(default="production", alias="APP_ENV")
    host: str = Field(default="0.0.0.0", alias="HOST")
    port: int = Field(default=8000, alias="PORT")
    version: str = "1.0.0"
    enable_docs: bool | None = Field(default=None, alias="ENABLE_DOCS")

    # LLM
    llm_provider: str = Field(default="", alias="LLM_PROVIDER")
    llm_api_key: str = Field(default="", alias="LLM_API_KEY")
    llm_model: str = Field(default="", alias="LLM_MODEL")

    # Network policy
    allow_localhost_for_tests: bool = Field(default=False, alias="ALLOW_LOCALHOST_FOR_TESTS")
    trusted_proxies: str = Field(default="", alias="TRUSTED_PROXIES")

    # Rate limiting
    rate_limit_requests: int = Field(default=5, alias="RATE_LIMIT_REQUESTS")
    rate_limit_window_s: int = Field(default=60, alias="RATE_LIMIT_WINDOW_S")

    # Concurrency
    max_concurrent_runs: int = 2
    run_queue_max: int = 10
    run_queue_timeout_s: int = 30

    # Timeouts
    default_run_timeout_s: int = 60
    heartbeat_timeout_s: int = 15

    # Limits
    max_prompt_chars: int = 1000
    max_pages_hard_cap: int = 25
    max_depth_hard_cap: int = 3
    max_links_hard_cap: int = 50
    response_size_cap: int = 1_048_576  # 1 MB

    # History
    max_run_history: int = 100

    # CORS
    allowed_origins: str = Field(default="", alias="ALLOWED_ORIGINS")

    # CLI paths (resolved relative to this file's location)
    cli_dir: Path = Path(__file__).parent.parent.parent / "cli"

    @property
    def cors_origins(self) -> list[str]:
        if self.allowed_origins.strip():
            return [o.strip() for o in self.allowed_origins.split(",") if o.strip()]
        if self.app_env == "production":
            return []
        return ["http://localhost:5173", "http://127.0.0.1:5173", "http://localhost:3000"]

    @property
    def docs_enabled(self) -> bool:
        if self.enable_docs is not None:
            return self.enable_docs
        return self.app_env != "production"

    @property
    def llm_mode(self) -> str:
        return "llm" if self.llm_api_key and self.llm_provider else "heuristic"

    @property
    def is_test(self) -> bool:
        return self.app_env == "test"

    @property
    def trusted_proxy_list(self) -> list[str]:
        return [p.strip() for p in self.trusted_proxies.split(",") if p.strip()]


_settings: Settings | None = None


def get_settings(reload: bool = False) -> Settings:
    global _settings
    if _settings is None or reload:
        _settings = Settings()
    return _settings
