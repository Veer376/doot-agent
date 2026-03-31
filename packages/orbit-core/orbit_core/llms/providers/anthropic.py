from __future__ import annotations

from typing import Any

from langchain_core.language_models.chat_models import BaseChatModel


def create_anthropic_chat_model(
    *,
    model: str,
    api_key: str | None = None,
    **kwargs: Any,
) -> BaseChatModel:
    """Create an Anthropic (Claude) chat model.

    Docs:
    - https://docs.langchain.com/oss/python/langchain/models
    - https://docs.langchain.com/oss/python/integrations/chat/anthropic

    The docs describe `ChatAnthropic(model=..., api_key=...)` with fallback
    to `ANTHROPIC_API_KEY` when `api_key` is not provided.
    """

    try:
        from langchain_anthropic import ChatAnthropic  # type: ignore
    except Exception as exc:  # pragma: no cover
        raise ImportError(
            "Anthropic provider requires optional dependency. "
            "Install with: pip install -U 'langchain[anthropic]'"
        ) from exc

    init_kwargs: dict[str, Any] = {"model": model, **kwargs}
    if api_key:
        init_kwargs.setdefault("api_key", api_key)

    try:
        return ChatAnthropic(**init_kwargs)
    except TypeError:
        # Backwards-compat fallback.
        if api_key:
            init_kwargs.pop("api_key", None)
            init_kwargs.setdefault("anthropic_api_key", api_key)
        return ChatAnthropic(**init_kwargs)
