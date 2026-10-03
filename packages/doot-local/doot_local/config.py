from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


DEFAULT_PROXY_URL = "http://127.0.0.1:8877"
DEFAULT_MODEL = "gemini-3.8-flash-low"


@dataclass(frozen=True)
class Settings:
    proxy_url: str
    api_key: str
    model: str
    timeout_seconds: float
    max_retries: int
    workspace_root: Path


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def load_settings() -> Settings:
    workspace = Path(
        os.environ.get("DOOT_WORKSPACE_ROOT", str(_repo_root()))
    ).expanduser().resolve()

    return Settings(
        proxy_url=os.environ.get("ANTIGRAVITY_BASE_URL", DEFAULT_PROXY_URL).rstrip("/"),
        api_key=os.environ.get("ANTIGRAVITY_API_KEY", "local-antigravity"),
        model=os.environ.get("ANTIGRAVITY_MODEL", DEFAULT_MODEL),
        timeout_seconds=float(os.environ.get("DOOT_MODEL_TIMEOUT_SECONDS", "90")),
        max_retries=int(os.environ.get("DOOT_MODEL_MAX_RETRIES", "1")),
        workspace_root=workspace,
    )
