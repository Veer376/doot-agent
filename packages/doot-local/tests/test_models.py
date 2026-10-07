from doot_local.models import (
    default_agent_model_context,
    prefixed_model_id,
    resolve_agent_model,
    runtime_model_id,
    LocalModel,
)


def test_local_model_prefix_round_trip():
    assert prefixed_model_id("claude-sonnet-4-6") == "local-claude-sonnet-4-6"
    assert runtime_model_id("local-claude-sonnet-4-6") == "claude-sonnet-4-6"


def test_resolve_agent_model_validates_policy():
    allowed = ["local-claude-sonnet-4-6", "local-gemini-3.8-flash-low"]
    assert (
        resolve_agent_model(
            "local-claude-sonnet-4-6",
            available_models=allowed,
            default_model="local-gemini-3.8-flash-low",
        )
        == "claude-sonnet-4-6"
    )

    try:
        resolve_agent_model(
            "local-claude-opus-4-6-thinking",
            available_models=allowed,
            default_model="local-gemini-3.8-flash-low",
        )
    except ValueError as exc:
        assert "not available for this agent" in str(exc)
    else:
        raise AssertionError("Expected disallowed model to fail validation")


def test_default_agent_model_context_uses_catalog(monkeypatch):
    monkeypatch.setattr(
        "doot_local.models.default_local_model_id",
        lambda: "local-gemini-3.8-flash-low",
    )
    models = [
        LocalModel(
            id="local-claude-sonnet-4-6",
            runtime_model="claude-sonnet-4-6",
            name="Claude Sonnet 4.6",
            provider="anthropic",
        ),
        LocalModel(
            id="local-gemini-3.8-flash-low",
            runtime_model="gemini-3.8-flash-low",
            name="Gemini 3.8 Flash Low",
            provider="google",
        ),
    ]

    assert default_agent_model_context(models) == {
        "available_models": [
            "local-claude-sonnet-4-6",
            "local-gemini-3.8-flash-low",
        ],
        "default_model": "local-gemini-3.8-flash-low",
    }
