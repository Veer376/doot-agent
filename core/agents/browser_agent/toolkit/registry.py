import inspect
import json
from urllib.parse import urlparse
from typing import Any, Callable, TYPE_CHECKING
from pydantic import BaseModel, create_model
from core.utils.logging_utils import get_agent_logger
from .types import FilterContext

# Use forward references
if TYPE_CHECKING:
    from core.browser_use.types import BrowserState
    from core.browser_use.context import BrowserContext
    from ..agent import AgentState, BrowserSnapshot
    from playwright.async_api import Page
    
logger = get_agent_logger("tool_registry")


class ToolRegistry:
    """A simple registry that filters tools using functions attached at registration."""

    def __init__(self):
        """Initializes the registry."""
        self.tools: dict[str, Callable] = {}
        self.filters: dict[str, Callable[[FilterContext], bool]] = {}

    def register(self, is_active: Callable[[FilterContext], bool] = None) -> Callable:
        """A decorator to register a tool function."""

        def decorator(func: Callable) -> Callable:
            tool_name = func.__name__

            # Ensure the tool has a docstring, as this is used by the LLM.
            if not inspect.getdoc(func):
                raise ValueError(
                    f"Tool '{tool_name}' must have a docstring to be registered."
                )

            self.tools[tool_name] = func

            # If a filter function was provided, store it.
            if is_active:
                self.filters[tool_name] = is_active

            return func

        return decorator

    def get_active_tools(
        self,
        agent_state: "AgentState",
    ) -> list[Callable]:
        """Builds a context from the current states and returns a list of active tools."""
        
        browser_snapshot: BrowserSnapshot = agent_state.get("browser_snapshot", {}) or {}

        raw_url = browser_snapshot.get("url", "")
        domain = urlparse(raw_url or "").hostname if raw_url else None

        if not domain:
            domain = "about:blank"

        context = FilterContext(
            domain=domain,
            step=agent_state.get('step', 0),
            last_action=agent_state.get('last_actions', [])[-1] if agent_state.get('last_actions', []) else None,
            reserved_tools=agent_state.get('reserved_tools', [])
        )

        active_tools = []
        tool_names = []

        for name, tool_func in self.tools.items():

            filter_func = self.filters.get(name)

            # A tool is active if it has NO filter, or if its filter returns True.
            if not filter_func or filter_func(context):
                active_tools.append(tool_func)
                tool_names.append(name)

        logger.info(f"Active tools: {tool_names}")
        return active_tools


tool_registry = ToolRegistry()
