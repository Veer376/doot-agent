import inspect
import json
import fnmatch
from urllib.parse import urlparse
from typing import Any, Callable, Dict, Optional, Type, Literal, List
from pydantic import BaseModel, create_model
from typing import TYPE_CHECKING
from logging_utils import get_agent_logger

# Use forward references
if TYPE_CHECKING:
    from ..agent import BrowserState, AgentState

logger = get_agent_logger("tool_registry")

class MetaData(BaseModel):
    allowed_domains: list[str] | None = None
    allowed_last_actions: list[str] | None = None
    allowed_steps: list[int] | None = None

class ToolRegistry:
  
    def __init__(self):
        self.tools_by_name: Dict[str, Callable[..., Any]] = {}
        self.tool_metadata: Dict[str, MetaData] = {}

    def register(
        self, metadata: MetaData|None = None
    ) -> Callable:
        """Decorator to register a tool function with conditions for its usage."""
        
        def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
            nonlocal metadata
            
            tool_name = func.__name__
            self.tools_by_name[tool_name] = func
            
            # --- Use the function's docstring as its description ---
            description = inspect.getdoc(func)
            if not description:
                raise ValueError(
                    f"Tool '{tool_name}' must have a docstring to be used as its description."
                )

            if not metadata:
                metadata = MetaData()
            
            self.tool_metadata[tool_name] = metadata

            return func

        return decorator
    
    def get_active_tools(
        self, browser_state: "BrowserState", agent_state: "AgentState"
    ) -> list[Callable]:
        """
        Gets a list of callable tool functions filtered by operation_mode and current URL.
        This is used for native tool-calling with .bind_tools().
        """
        # current_domain = urlparse(current_url).netloc if current_url else ""
        
        active_tools = []
        active_tool_names = []
        
        for name, metadata in self.tool_metadata.items():
            
            # is_{condition}_allowed_for_this_tool
            
            if not self.is_domain_allowed(browser_state.url, metadata.allowed_domains):
                continue
            
            if not self.is_last_action_allowed(agent_state.get("last_action", None), metadata.allowed_last_actions):
                continue
            
            if not self.is_step_allowed(agent_state.get("step", None), metadata.allowed_steps):
                continue
            
            active_tools.append(self.tools_by_name[name])
            active_tool_names.append(name)
        
        logger.debug(f"Active tools: {active_tool_names}")
        return active_tools
    
    
    def is_domain_allowed(
        self, current_url: str, allowed_domains: list[str] | None
    ) -> bool:
        """Check if the current URL matches any of the allowed domains."""
        if not allowed_domains or not current_url:
            return True  # No restrictions

        try:
            
            if current_url.startswith("about:") or current_url.startswith("chrome://"):
                return current_url in allowed_domains
            
            from urllib.parse import urlparse
            
            parsed = urlparse(current_url)
            current_domain = parsed.hostname
            
            if not current_domain:
                return False  # invalid URL
            
            return any(current_domain==domain for domain in allowed_domains)
        
        except Exception:
            return False

    def is_last_action_allowed(
        self, last_action: str | None, allowed_last_actions: list[str] | None
    ) -> bool:
        """Check if the last action matches any of the required actions."""
        if not allowed_last_actions or not last_action:
            return True
        
        return last_action in allowed_last_actions
    
    def is_step_allowed(
        self, step: int|None, allowed_steps: list[int]|None
    ) -> bool:
        """Check if the current step is allowed."""
        if not allowed_steps or step is None:
            return True
        
        return step in allowed_steps
    
    
tool_registry = ToolRegistry()