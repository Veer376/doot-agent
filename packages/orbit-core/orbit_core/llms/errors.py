from __future__ import annotations


class MissingApiKeyError(RuntimeError):
    def __init__(self, provider: str, env_vars: list[str] | None = None):
        self.provider = provider
        self.env_vars = env_vars or []
        hint = (
            f"Set one of: {', '.join(self.env_vars)}"
            if self.env_vars
            else "Set the API key."
        )
        super().__init__(f"[MISSING_API_KEY:{provider}] {hint}")


class UnsupportedModelProviderError(ValueError):
    def __init__(self, provider: str, model: str):
        self.provider = provider
        self.model = model
        super().__init__(f"Unsupported provider '{provider}' for model '{model}'.")
