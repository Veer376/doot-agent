from __future__ import annotations

import logging
import os
from collections.abc import Mapping
from typing import Any

from langchain_core.language_models.chat_models import BaseChatModel

from orbit_core.llms.errors import MissingApiKeyError
from orbit_core.llms.model_spec import (
    Provider,
    infer_provider_from_model_name,
    parse_model_id,
)
from orbit_core.llms.providers import (
    create_anthropic_chat_model,
    create_fake_chat_model,
    create_google_genai_chat_model,
    create_openai_chat_model,
)

logger = logging.getLogger(__name__)


_ENV_KEYS_BY_PROVIDER: dict[Provider, list[str]] = {
    "openai": ["OPENAI_API_KEY"],
    "anthropic": ["ANTHROPIC_API_KEY"],
    # LangChain docs use GOOGLE_API_KEY; this repo also sometimes uses GEMINI_API_KEY.
    "google_genai": ["GOOGLE_API_KEY", "GEMINI_API_KEY"],
    "google_vertexai": ["GOOGLE_API_KEY", "GEMINI_API_KEY"],
    # Fake provider is in-memory; no API keys required.
    "fake": [],
}


def _get_api_key_from_env(provider: Provider) -> str | None:
    for env_key in _ENV_KEYS_BY_PROVIDER.get(provider, []):
        value = os.environ.get(env_key)
        if value:
            return value
    return None


def get_model_instance(
    model_id: str | None,
    *,
    default_model: str | None = None,
    api_keys: Mapping[str, str] | None = None,
    require_api_key: bool = True,
    **kwargs: Any,
) -> BaseChatModel | str:
    """Resolve a LangChain chat model from a `provider:model` identifier.

    Mirrors the behavior of the reference JS `getModelInstance()`:
    - If `model_id` includes an explicit provider prefix (e.g. `openai:gpt-5.2`)
      we respect it.
    - If no provider is specified, we infer it from the model name prefix.
    - If the provider is recognized, we return a provider-specific LangChain
      chat model instance.
    - Otherwise, we return the unresolved model string (caller can decide what
      to do).

    This is intentionally compatible with LangChain's documented model
    initialization patterns:
    - `init_chat_model("google_genai:gemini-2.5-flash-lite")`
    - `ChatOpenAI(model="gpt-5.2")`, `ChatAnthropic(model="claude-sonnet-4-6")`,
      `ChatGoogleGenerativeAI(model="gemini-2.5-flash-lite")`

    Docs:
    - https://docs.langchain.com/oss/python/langchain/models

    Args:
        model_id: Model identifier, optionally namespaced as `provider:model`.
        default_model: Used when `model_id` is None.
        api_keys: Optional mapping for per-provider API keys. Supported keys:
            - "openai", "anthropic", "google"/"google_genai"
            - "OPENAI_API_KEY", "ANTHROPIC_API_KEY", "GOOGLE_API_KEY", "GEMINI_API_KEY"
        require_api_key: If True, raises MissingApiKeyError when a provider is
            recognized but no API key is found.
        **kwargs: Additional kwargs forwarded to the provider model constructor.

    Returns:
        A `BaseChatModel` instance when the provider is recognized, otherwise
        the unresolved model string.

    Raises:
        MissingApiKeyError: If `require_api_key=True` and key is missing.
        ValueError: If both `model_id` and `default_model` are None.
    """

    raw = model_id or default_model
    if raw is None:
        raise ValueError("model_id is required when default_model is not set")

    parsed = parse_model_id(raw)
    provider = parsed.provider or infer_provider_from_model_name(parsed.model)

    logger.info(
        "[LLM] Using model: %s (provider: %s)",
        parsed.model,
        provider or "auto-detect",
    )

    if provider is None:
        return parsed.model

    if provider == "fake":
        # In-memory fake model used for tests; never requires an API key.
        return create_fake_chat_model(model=parsed.model, **kwargs)

    # allow callers to provide API keys in a dict without forcing env vars
    api_key: str | None = None
    if api_keys:
        api_key = (
            api_keys.get(provider)
            or api_keys.get("google")
            or api_keys.get(provider.replace("_", "-"))
            or api_keys.get("OPENAI_API_KEY")
            or api_keys.get("ANTHROPIC_API_KEY")
            or api_keys.get("GOOGLE_API_KEY")
            or api_keys.get("GEMINI_API_KEY")
        )

    api_key = api_key or _get_api_key_from_env(provider)

    if require_api_key and not api_key:
        raise MissingApiKeyError(provider, _ENV_KEYS_BY_PROVIDER.get(provider, []))

    # If the caller allows missing keys, don't instantiate provider SDK clients.
    # Return the unresolved model string so higher-level code can decide how to proceed.
    if not require_api_key and not api_key:
        return parsed.model

    if provider == "openai":
        return create_openai_chat_model(model=parsed.model, api_key=api_key, **kwargs)

    if provider == "anthropic":
        return create_anthropic_chat_model(
            model=parsed.model, api_key=api_key, **kwargs
        )

    if provider == "google_genai":
        return create_google_genai_chat_model(
            model=parsed.model, api_key=api_key, **kwargs
        )

    # VertexAI is supported elsewhere in the repo but isn't requested in the JS reference.
    return parsed.model
