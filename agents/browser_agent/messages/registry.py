from typing import Callable, TYPE_CHECKING
from pydantic import BaseModel, Field

if TYPE_CHECKING:
    from ..agent import AgentState


class Context(BaseModel):
    consecutive_failures: list[str]
    max_consecutive_failures: int


class MessageRegistry:
    """Registry for conditional messages that can be injected into the agent's system prompt."""

    def __init__(self):
        self.messages = []

    def register(self, message: str, is_active: Callable[[Context], bool]) -> None:
        """Register a new message with a condition that determines when it should be injected."""
        self.messages.append((message, is_active))

    def get_active_messages(self, agent_state: "AgentState") -> list[str]:
        """Get all messages that should be active based on the current agent state."""
        context = Context(
            consecutive_failures=agent_state.get("consecutive_failures", []) or [],
            max_consecutive_failures=2,
        )
        active_messages = [message for message, is_active in self.messages if is_active(context)]
        # FIXME: Build more robust approach to clear the previous error messages.
        self.messages = [] 
        return active_messages


# Create a singleton instance of the registry to be used across the application
message_registry = MessageRegistry()
