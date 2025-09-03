from abc import abstractmethod
import os
from dotenv import load_dotenv
from typing import Callable, TypeVar, Generic
from langchain_core.messages import AIMessage, BaseMessage
from typing import TypeVar, Generic
from google.genai import types
from langchain_core.messages import BaseMessage
from abc import abstractmethod, ABC
from dataclasses import dataclass
from typing import Literal


class MessageBlueprintBase(ABC):
    """Base class for messages used get next response from LLMs."""

    @abstractmethod
    def to_gemini_format(self) -> tuple[str, list[types.Content], list[Callable]]:
        """Convert the message blueprint to the Gemini API format.
        Returns:
            tuple: A tuple containing the system instructions, list of content parts and list of tools.
            
        """
        pass

    @abstractmethod
    def to_langchain_format(self) -> tuple[list[BaseMessage], list[Callable]]:
        """Convert the message blueprint to the LangChain format.
        Returns:
            tuple: A list of LangChain messages and a list of tools.
        """
        pass


@dataclass
class LLMConfig:
    """Configuration for LLMs."""

    thinking_budget: int = 0
    temperature: float = 0.5


class LLM:
    """Base class for all LLM wrappers."""

    load_dotenv()

    def __init__(self, model_name: str, provider: str = None):
        self.model_name = model_name or os.getenv("MODEL_NAME", "gemini-2.5-flash")
        self.provider = provider or os.getenv("MODEL_PROVIDER", "google")

    @abstractmethod
    async def __call__(
        self,
        message_plan: MessageBlueprintBase,
        config: LLMConfig | None = None,
    ) -> AIMessage:
        """Call the LLM with the given tools and message plan."""
        pass


class GeminiMessage(AIMessage):
    """Extended AIMessage with gemini attributes."""

    thought: str | None
    parts: list[types.PartDict] = []


class LLMUsageStats:

    def __init__(self, usd_to_inr: float = 85.0):
        """Initialize the LLM usage stats tracker."""

        self.usd_to_inr = usd_to_inr
        # CALLS
        self.calls: dict[str, int] = {}  # Track calls by model name
        self.total_calls: int = 0  # Total number of calls across all models
        # TOKENS
        self.input_tokens: dict[str, int] = {}  # {"TEXT": 123, "IMAGE": 234}
        self.thought_tokens: int = 0
        self.tool_tokens: int = 0
        self.output_tokens: int = (
            0  # candidate tokens with response and function calls.
        )
        self.total_tokens: int = 0
        # COST
        self.input_cost: float = 0.0
        self.output_cost: float = 0.0
        self.total_cost: float = 0.0

        self.model_costs = {
            "gemini-2.5-pro": {
                "input": 1.25,
                "output": 10.0,
            },
            "gemini-2.5-flash": {
                "input": 0.3,
                "output": 2.5,
            },
            "gemini-2.5-flash-lite": {
                "input": 0.1,
                "output": 1.0,
            },
        }

    def update_from_gemini(self, model_name: str, usage_metadata):
        # Update call count
        self.calls[model_name] = self.calls.get(model_name, 0) + 1
        self.total_calls += 1

        # Update input tokens by modality
        total_input_tokens = 0
        if hasattr(usage_metadata, "prompt_tokens_details"):
            for item in usage_metadata.prompt_tokens_details:
                modality = (
                    str(item.modality) if hasattr(item, "modality") else "UNKNOWN"
                )
                count = getattr(item, "token_count", 0) or 0  # Ensure it's an integer
                if modality:
                    self.input_tokens[modality] = (
                        self.input_tokens.get(modality, 0) + count
                    )
                    total_input_tokens += count

        # Update other token types - ensure we have integers not None values
        thought_tokens = getattr(usage_metadata, "thoughts_token_count", 0)
        self.thought_tokens += thought_tokens if thought_tokens else 0

        tool_tokens = getattr(usage_metadata, "tool_use_prompt_token_count", 0)
        self.tool_tokens += tool_tokens if tool_tokens else 0

        # Output tokens (candidates)
        output_tokens = getattr(usage_metadata, "candidates_token_count", 0)
        self.output_tokens += output_tokens if output_tokens else 0

        # Total tokens
        total = getattr(usage_metadata, "total_token_count", 0)
        self.total_tokens += total if total else 0

        # Calculate costs separately for input and output
        self._update_cost(model_name, total_input_tokens, output_tokens)

    def update_from_langgraph(self, model_name: str, usage_metadata: dict):
        # Update call count
        self.calls[model_name] = self.calls.get(model_name, 0) + 1
        self.total_calls += 1

        # Update input tokens
        input_count = usage_metadata.get("input_tokens", 0)
        self.input_tokens["TEXT"] = self.input_tokens.get("TEXT", 0) + input_count

        # Update output tokens
        output_count = usage_metadata.get("output_tokens", 0)
        self.output_tokens += output_count

        # Update total tokens
        total = usage_metadata.get("total_tokens", 0)
        self.total_tokens += total

        # Calculate costs separately for input and output
        self._update_cost(model_name, input_count, output_count)

    def _update_cost(self, model_name: str, input_tokens: int, output_tokens: int):
        model_rates = self.model_costs.get(model_name)
        if model_rates is None:
            # Skip cost calculation if cost isn't defined
            return

        # Ensure tokens are not None
        input_tokens = input_tokens or 0
        output_tokens = output_tokens or 0

        # Calculate input cost (per 1M tokens)
        input_cost_usd = (input_tokens / 1_000_000) * model_rates["input"]
        input_cost_inr = input_cost_usd * self.usd_to_inr

        # Calculate output cost (per 1M tokens)
        output_cost_usd = (output_tokens / 1_000_000) * model_rates["output"]
        output_cost_inr = output_cost_usd * self.usd_to_inr

        # Update costs
        self.input_cost += input_cost_inr
        self.output_cost += output_cost_inr
        self.total_cost = self.input_cost + self.output_cost

    def get_stats(self) -> dict:
        """Get comprehensive usage statistics."""
        return {
            # Calls
            "calls_by_model": self.calls,
            "total_calls": self.total_calls,
            # Tokens
            "input_tokens": self.input_tokens,
            "thought_tokens": self.thought_tokens,
            "tool_tokens": self.tool_tokens,
            "output_tokens": self.output_tokens,
            "total_tokens": self.total_tokens,
            # Cost
            "input_cost_inr": self.input_cost,
            "output_cost_inr": self.output_cost,
            "total_cost_inr": self.total_cost,
            "total_cost_usd": self.total_cost / self.usd_to_inr,
        }
