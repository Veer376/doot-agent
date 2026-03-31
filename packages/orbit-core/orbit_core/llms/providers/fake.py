from __future__ import annotations

import json
import os
from collections.abc import Iterable, Iterator
from typing import Any

from langchain_core.language_models.chat_models import BaseChatModel


def _iter_default_messages(model: str) -> Iterator[str]:
    """Default fake outputs.

    This is intentionally simple and deterministic so it can be used in tests
    without network calls.

    You can override via:
    - Passing `messages=[...]` to `create_fake_chat_model`
    - Setting `ORBIT_FAKE_LLM_MESSAGES` to a JSON array of strings

    LangChain docs recommend `GenericFakeChatModel` for mocking chat models:
    https://docs.langchain.com/oss/python/langchain/test
    """

    # Optional global override for convenience in CLI testing.
    env = os.environ.get("ORBIT_FAKE_LLM_MESSAGES")
    if env:
        try:
            parsed = json.loads(env)
            if isinstance(parsed, list) and all(isinstance(x, str) for x in parsed):
                return iter(parsed)
        except Exception:
            pass

    # Provide a stable, recognizable response.
    return iter([f"[fake:{model}] ok"])


def create_fake_chat_model(
    *,
    model: str = "fake",
    messages: Iterable[str] | None = None,
    **_: Any,
) -> BaseChatModel:
    """Create a fake chat model (no API calls).

    Uses LangChain's `GenericFakeChatModel`, which consumes an iterator of
    responses and yields one per invocation.

    Docs:
    - https://docs.langchain.com/oss/python/langchain/test

    Args:
        model: Identifier string (used only for labeling default output).
        messages: Iterable of strings to return in order.

    Returns:
        A `BaseChatModel` instance usable by LangChain agents.
    """

    try:
        from langchain_core.language_models.fake_chat_models import (  # type: ignore
            GenericFakeChatModel,
        )
    except Exception as exc:  # pragma: no cover
        raise ImportError(
            "Fake chat model requires langchain-core. Install via `pip install langchain` "
            "or ensure langchain-core is available."
        ) from exc

    iterator = iter(messages) if messages is not None else _iter_default_messages(model)
    return GenericFakeChatModel(messages=iterator)
