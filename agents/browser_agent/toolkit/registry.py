import inspect
import json
from urllib.parse import urlparse
from typing import Any, Callable, TYPE_CHECKING
from pydantic import BaseModel, create_model
from logging_utils import get_agent_logger
from .types import FilterContext

# Use forward references
if TYPE_CHECKING:
    from browser_use.types import BrowserState
    from browser_use.context import BrowserContext
    from ..agent import AgentState, AgentContext
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

    async def get_active_tools(
        self,
        agent_context: "AgentContext",
        agent_state: "AgentState",
    ) -> list[Callable]:
        """Builds a context from the current states and returns a list of active tools."""
        
        browser_context: BrowserContext = agent_context.browser_context
        browser_state: BrowserState = browser_context.current_state
        
        domain = urlparse(browser_state.url).hostname

        if not domain:
            domain = "about:blank"

        # Get the current page from browser context
        page = None
        try:
            page = await browser_context.get_agent_current_page()
        except Exception as e:
            logger.error(f"Error getting current page: {e}")

        # Check if text field is focused
        text_field_focused = (
            await browser_context.is_text_field_focused(page) if page else False
        )

        context = FilterContext(
            domain=domain,
            step=agent_state.step,
            last_action=agent_state.last_actions[-1] if agent_state.last_actions else None,
            text_field_focused=text_field_focused,
            reserved_tools=agent_state.reserved_tools
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
