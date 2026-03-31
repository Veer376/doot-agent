from __future__ import annotations

import os
from typing import Any

from langchain_core.language_models.chat_models import BaseChatModel


def create_google_genai_chat_model(
    *,
    model: str,
    api_key: str | None = None,
    **kwargs: Any,
) -> BaseChatModel:
    """Create a Google GenAI (Gemini) chat model.

    LangChain docs show:
    - `from langchain_google_genai import ChatGoogleGenerativeAI`
    - `init_chat_model("google_genai:gemini-...")`

    This helper uses `ChatGoogleGenerativeAI` to allow passing provider-specific
    kwargs like `include_thoughts` and `thinking_budget` (supported by
    `langchain-google-genai`).

    Docs:
    - https://docs.langchain.com/oss/python/langchain/models
    - https://docs.langchain.com/oss/python/integrations/chat/google_genai

    Note: The canonical environment variable is `GOOGLE_API_KEY`.
    """

    try:
        from langchain_google_genai import ChatGoogleGenerativeAI  # type: ignore
    except Exception as exc:  # pragma: no cover
        raise ImportError(
            "Google GenAI provider requires optional dependency. "
            "Install with: pip install -U 'langchain[google-genai]'"
        ) from exc

    init_kwargs: dict[str, Any] = {"model": model, **kwargs}

    if api_key:
        # Prefer explicit key if supported; otherwise set env var as fallback.
        init_kwargs.setdefault("google_api_key", api_key)

    try:
        return ChatGoogleGenerativeAI(**init_kwargs)
    except TypeError:
        # Some versions may not accept `google_api_key`; fall back to env var.
        if api_key and not os.environ.get("GOOGLE_API_KEY"):
            os.environ["GOOGLE_API_KEY"] = api_key
        init_kwargs.pop("google_api_key", None)
        return ChatGoogleGenerativeAI(**init_kwargs)
