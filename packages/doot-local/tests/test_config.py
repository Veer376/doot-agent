from pathlib import Path

from doot_local.config import DEFAULT_MODEL, DEFAULT_PROXY_URL, load_settings


def test_defaults_point_to_local_antigravity(monkeypatch):
    for name in (
        "ANTIGRAVITY_BASE_URL",
        "ANTIGRAVITY_API_KEY",
        "ANTIGRAVITY_MODEL",
        "DOOT_MODEL_TIMEOUT_SECONDS",
        "DOOT_MODEL_MAX_RETRIES",
        "DOOT_WORKSPACE_ROOT",
    ):
        monkeypatch.delenv(name, raising=False)

    settings = load_settings()

    assert settings.proxy_url == DEFAULT_PROXY_URL
    assert settings.model == DEFAULT_MODEL
    assert settings.api_key
    assert settings.workspace_root == Path(__file__).resolve().parents[3]
