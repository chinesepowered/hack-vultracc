"""Settings, read once from the environment (and .env at the repo root for local runs)."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

REPO_ROOT = Path(__file__).resolve().parents[3]
load_dotenv(REPO_ROOT / ".env")


def _env(name: str, default: str = "") -> str:
    return os.environ.get(name, default).strip()


@dataclass(frozen=True)
class Settings:
    inference_base_url: str = field(default_factory=lambda: _env("VULTR_INFERENCE_BASE_URL", "https://api.vultrinference.com/v1"))
    inference_api_key: str = field(default_factory=lambda: _env("VULTR_INFERENCE_API_KEY"))
    model_main: str = field(default_factory=lambda: _env("LLM_MODEL_MAIN"))
    model_fast: str = field(default_factory=lambda: _env("LLM_MODEL_FAST"))
    model_safety: str = field(default_factory=lambda: _env("LLM_MODEL_SAFETY"))
    database_url: str = field(default_factory=lambda: _env("DATABASE_URL", "sqlite:///./tieout-dev.db"))
    s3_endpoint: str = field(default_factory=lambda: _env("S3_ENDPOINT"))
    s3_access_key: str = field(default_factory=lambda: _env("S3_ACCESS_KEY"))
    s3_secret_key: str = field(default_factory=lambda: _env("S3_SECRET_KEY"))
    s3_bucket: str = field(default_factory=lambda: _env("S3_BUCKET"))
    s3_region: str = field(default_factory=lambda: _env("S3_REGION", "sjc1"))
    local_storage_dir: str = field(default_factory=lambda: _env("LOCAL_STORAGE_DIR", str(REPO_ROOT / ".local-storage")))
    runner_url: str = field(default_factory=lambda: _env("SANDBOX_RUNNER_URL", "http://127.0.0.1:7070"))
    runner_token: str = field(default_factory=lambda: _env("SANDBOX_RUNNER_TOKEN"))
    sandbox_image: str = field(default_factory=lambda: _env("SANDBOX_IMAGE", "tieout-sandbox:latest"))
    app_base_url: str = field(default_factory=lambda: _env("APP_BASE_URL", "http://localhost:8000"))
    session_secret: str = field(default_factory=lambda: _env("SESSION_SECRET", "dev-only-secret-change-me"))
    max_concurrent_sandboxes: int = field(default_factory=lambda: int(_env("MAX_CONCURRENT_SANDBOXES", "16")))
    max_concurrent_runs: int = field(default_factory=lambda: int(_env("MAX_CONCURRENT_RUNS", "12")))
    daily_token_budget: int = field(default_factory=lambda: int(_env("DAILY_TOKEN_BUDGET", "5000000")))
    max_tool_calls: int = field(default_factory=lambda: int(_env("AGENT_MAX_TOOL_CALLS", "14")))
    run_timeout_s: int = field(default_factory=lambda: int(_env("AGENT_RUN_TIMEOUT_S", "300")))
    exec_timeout_s: int = field(default_factory=lambda: int(_env("AGENT_EXEC_TIMEOUT_S", "60")))
    batches_per_user_per_hour: int = field(default_factory=lambda: int(_env("BATCHES_PER_USER_PER_HOUR", "20")))
    data_dir: str = field(default_factory=lambda: _env("DEMO_DATA_DIR", str(REPO_ROOT / "data" / "demo")))
    prompts_dir: str = field(default_factory=lambda: _env("PROMPTS_DIR", str(REPO_ROOT / "prompts")))
    web_dist: str = field(default_factory=lambda: _env("WEB_DIST", str(REPO_ROOT / "apps" / "web" / "dist")))
    region_label: str = field(default_factory=lambda: _env("REGION_LABEL", "Vultr Silicon Valley (sjc)"))
    cookie_secure: bool = field(default_factory=lambda: _env("COOKIE_SECURE", "0") == "1")


settings = Settings()
