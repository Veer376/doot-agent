from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

Provider = Literal[
    "openai",
    "anthropic",
    "google_genai",
    "google_vertexai",
    "fake",
]


_PROVIDER_ALIASES: dict[str, Provider] = {
    # Canonical
    "openai": "openai",
    "anthropic": "anthropic",
    "google_genai": "google_genai",
    "google_vertexai": "google_vertexai",
    # Common shorthands / JS naming
    "google": "google_genai",
    "gemini": "google_genai",
    "vertex": "google_vertexai",
    "vertexai": "google_vertexai",
    # Sometimes users paste the JS integration package id
    "google-genai": "google_genai",
    # Testing
    "fake": "fake",
}


@dataclass(frozen=True)
class ParsedModelId:
    raw: str
    provider: Provider | None
    model: str


def normalize_provider(provider: str) -> Provider | None:
    return _PROVIDER_ALIASES.get(provider.strip().lower())


def parse_model_id(model_id: str) -> ParsedModelId:
    raw = model_id.strip()
    if not raw:
        raise ValueError("model_id must be non-empty")

    provider: Provider | None = None
    model = raw

    if ":" in raw:
        provider_part, model_part = raw.split(":", 1)
        maybe_provider = normalize_provider(provider_part)
        if maybe_provider is not None and model_part.strip():
            provider = maybe_provider
            model = model_part.strip()

    return ParsedModelId(raw=raw, provider=provider, model=model)


def infer_provider_from_model_name(model: str) -> Provider | None:
    lower = model.lower()

    # Testing provider (no network calls). Useful for validating agent logic.
    if lower == "fake" or lower.startswith("fake-"):
        return "fake"

    if lower.startswith("claude"):
        return "anthropic"

    if lower.startswith(("gpt", "o1", "o3", "o4")):
        return "openai"

    if lower.startswith("gemini"):
        return "google_genai"

    return None
