from __future__ import annotations

from typing import Any

from langchain_core.language_models.chat_models import BaseChatModel


def create_openai_chat_model(
    *,
    model: str,
    api_key: str | None = None,
    **kwargs: Any,
) -> BaseChatModel:
    """Create an OpenAI chat model.

    LangChain docs show two standard ways to initialize models:
    - Provider-specific class: `from langchain_openai import ChatOpenAI`
    - Generic initializer: `from langchain.chat_models import init_chat_model`

    This helper prefers the provider-specific class when available.

    Docs:
    - https://docs.langchain.com/oss/python/langchain/models
    - https://docs.langchain.com/oss/python/integrations/chat/openai
    """

    try:
        from langchain_openai import ChatOpenAI  # type: ignore
    except Exception as exc:  # pragma: no cover
        raise ImportError(
            "OpenAI provider requires optional dependency. "
            "Install with: pip install -U 'langchain[openai]'"
        ) from exc

    init_kwargs: dict[str, Any] = {"model": model, **kwargs}
    if api_key:
        # Newer versions use `api_key`; older versions used `openai_api_key`.
        init_kwargs.setdefault("api_key", api_key)

    try:
        return ChatOpenAI(**init_kwargs)
    except TypeError:
        # Backwards-compat fallback.
        if api_key:
            init_kwargs.pop("api_key", None)
            init_kwargs.setdefault("openai_api_key", api_key)
        return ChatOpenAI(**init_kwargs)
