"""Minimal runtime helpers for managing a single browser instance.

This module provides a thin abstraction over the browser configuration
so that graph nodes can obtain an active ``BrowserContext`` without having
to store the non-serialisable object in graph state.
"""

from __future__ import annotations

import os
import platform
from pathlib import Path
from typing import TYPE_CHECKING, Optional

from core.browser_use.browser import Browser, BrowserConfig
from core.browser_use.context import BrowserContext, BrowserContextConfig

if TYPE_CHECKING:  # pragma: no cover
    from .state import AgentContext


_active_browser: Optional[Browser] = None
_active_context: Optional[BrowserContext] = None


async def get_browser_context(agent_context: "AgentContext") -> BrowserContext:
    """Return an active ``BrowserContext``.

    For now we maintain a single shared context that is reused across
    invocations. Production variants can replace this with a pool manager.
    """

    global _active_browser, _active_context

    if agent_context is not None and agent_context.get("browser_context", None) is not None:
        return agent_context.get("browser_context")

    if _active_context is not None:
        return _active_context

    browser_config = agent_context.get("browser_config", None) if agent_context is not None else None
    context_config = agent_context.get("browser_context_config", None) if agent_context is not None else None

    if _active_browser is None:
        resolved_config = browser_config or BrowserConfig(
            browser_binary_path="C:/Program Files/Google/Chrome/Application/chrome.exe"
        )
        _active_browser = Browser(config=resolved_config)

    _active_context = await _active_browser.new_context(
        config=context_config or BrowserContextConfig(highlight_elements=True)
    )

    return _active_context
