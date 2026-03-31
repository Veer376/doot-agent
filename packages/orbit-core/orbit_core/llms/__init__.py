from __future__ import annotations

"""LLM utilities.

This package provides a small factory for resolving LangChain chat model
instances from a `provider:model` identifier (e.g. `openai:gpt-5.2`,
`anthropic:claude-sonnet-4-6`, `google_genai:gemini-2.5-flash-lite`).

See LangChain docs: https://docs.langchain.com/oss/python/langchain/models
"""

from orbit_core.llms.factory import get_model_instance

__all__ = ["get_model_instance"]
