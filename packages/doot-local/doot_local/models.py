from __future__ import annotations

import json
import threading
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any

from .config import load_settings


LOCAL_MODEL_PREFIX = "local-"
MODEL_CACHE_TTL_SECONDS = 30.0


@dataclass(frozen=True)
class LocalModel:
    id: str
    runtime_model: str
    name: str
    provider: str
    description: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "runtime_model": self.runtime_model,
            "name": self.name,
            "provider": self.provider,
            "description": self.description,
            "source": "local",
        }


_cache_lock = threading.Lock()
_cached_models: list[LocalModel] = []
_cached_at = 0.0


def prefixed_model_id(runtime_model: str) -> str:
    if runtime_model.startswith(LOCAL_MODEL_PREFIX):
        return runtime_model
    return f"{LOCAL_MODEL_PREFIX}{runtime_model}"


def runtime_model_id(model_id: str) -> str:
    if model_id.startswith(LOCAL_MODEL_PREFIX):
        return model_id[len(LOCAL_MODEL_PREFIX) :]
    return model_id


def _provider_for_model(model_id: str) -> str:
    lowered = model_id.lower()
    if lowered.startswith("claude"):
        return "anthropic"
    if lowered.startswith("gemini"):
        return "google"
    if lowered.startswith("gpt") or lowered.startswith("o1") or lowered.startswith("o3"):
        return "openai"
    return "custom"


def _display_name(model_id: str, description: str | None) -> str:
    if description and description.strip() and description.strip() != model_id:
        return description.strip()
    return model_id.replace("-", " ").title()


def _fetch_proxy_models() -> list[LocalModel]:
    settings = load_settings()
    request = urllib.request.Request(
        f"{settings.proxy_url.rstrip('/')}/v1/models",
        headers={"accept": "application/json"},
    )
    try:
        with urllib.request.urlopen(request, timeout=8) as response:
            payload = json.load(response)
    except (urllib.error.URLError, TimeoutError, OSError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"Could not load local models from proxy: {exc}") from exc

    models: list[LocalModel] = []
    seen: set[str] = set()
    for raw in payload.get("data", []):
        if not isinstance(raw, dict):
            continue
        runtime_id = str(raw.get("id") or "").strip()
        if not runtime_id or runtime_id in seen:
            continue
        seen.add(runtime_id)
        description = raw.get("description")
        description_text = str(description).strip() if description else None
        models.append(
            LocalModel(
                id=prefixed_model_id(runtime_id),
                runtime_model=runtime_id,
                name=_display_name(runtime_id, description_text),
                provider=_provider_for_model(runtime_id),
                description=description_text,
            )
        )

    return models


def local_models(*, force_refresh: bool = False) -> list[LocalModel]:
    global _cached_at, _cached_models

    now = time.monotonic()
    with _cache_lock:
        if (
            not force_refresh
            and _cached_models
            and now - _cached_at < MODEL_CACHE_TTL_SECONDS
        ):
            return list(_cached_models)

    models = _fetch_proxy_models()
    with _cache_lock:
        _cached_models = list(models)
        _cached_at = time.monotonic()
    return models


def default_local_model_id() -> str:
    return prefixed_model_id(load_settings().model)


def default_agent_model_context(models: list[LocalModel] | None = None) -> dict[str, Any]:
    available = models if models is not None else local_models()
    available_ids = [model.id for model in available]
    default_model = default_local_model_id()
    if default_model not in available_ids and available_ids:
        default_model = available_ids[0]
    return {
        "available_models": available_ids,
        "default_model": default_model if available_ids else None,
    }


def resolve_agent_model(
    selected_model: str | None,
    *,
    available_models: list[str] | None = None,
    default_model: str | None = None,
) -> str:
    selected = selected_model or default_model or default_local_model_id()
    if available_models and selected not in available_models:
        raise ValueError(f"Model {selected!r} is not available for this agent")
    return runtime_model_id(selected)
