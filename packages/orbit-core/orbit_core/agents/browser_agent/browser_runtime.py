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

from orbit_core.browser_use.browser import Browser, BrowserConfig
from orbit_core.browser_use.context import BrowserContext, BrowserContextConfig

if TYPE_CHECKING:  # pragma: no cover
    from .state import AgentContext


_active_browser: Optional[Browser] = None
_active_context: Optional[BrowserContext] = None


def _is_in_docker() -> bool:
    """Check if we're running inside a Docker container."""
    # Check for .dockerenv file
    if os.path.exists('/.dockerenv'):
        return True
    
    # Check for IN_DOCKER environment variable
    if os.environ.get('IN_DOCKER', '').lower() in ('true', '1', 'yes', 't', 'y'):
        return True
    
    # Check cgroup for docker
    try:
        with open('/proc/self/cgroup', 'r') as f:
            return 'docker' in f.read()
    except Exception:
        pass
    
    return False


def _get_browser_wss_url() -> Optional[str]:
    """Get the browser WebSocket URL from environment or Docker service."""
    # First check environment variable
    wss_url = os.environ.get('BROWSER_WSS_URL')
    if wss_url:
        # Use the URL as-is from environment
        # The browser server writes the correct endpoint to the file
        return wss_url
    
    # If in Docker, try to construct from service name
    if _is_in_docker():
        # Default Docker Compose service name and port
        browser_host = os.environ.get('BROWSER_HOST', 'browser')
        browser_port = os.environ.get('PLAYWRIGHT_PORT', '3500')
        # Just use the base URL - Playwright will handle the rest
        return f'ws://{browser_host}:{browser_port}/'
    
    return None


async def get_browser_context(agent_context: "AgentContext") -> BrowserContext:
    """Return an active ``BrowserContext``.

    For now we maintain a single shared context that is reused across
    invocations. Production variants can replace this with a pool manager.
    
    If running in Docker, connects to the browser service via WebSocket.
    Otherwise, launches a local browser instance.
    """

    global _active_browser, _active_context

    if agent_context is not None and agent_context.get("browser_context", None) is not None:
        return agent_context.get("browser_context")

    if _active_context is not None:
        return _active_context

    browser_config = agent_context.get("browser_config", None) if agent_context is not None else None
    context_config = agent_context.get("browser_context_config", None) if agent_context is not None else None

    if _active_browser is None:
        # Determine if we should connect to remote browser or launch locally
        in_docker = _is_in_docker()
        wss_url = _get_browser_wss_url()
        
        if in_docker and wss_url:
            # Connect to Docker browser service via WebSocket
            resolved_config = browser_config or BrowserConfig(
                wss_url=wss_url
            )
        else:
            # Launch local browser instance
            # Platform-specific binary path for local development
            browser_binary = None
            if platform.system() == 'Windows':
                # Common Chrome paths on Windows
                possible_paths = [
                    "C:/Program Files/Google/Chrome/Application/chrome.exe",
                    "C:/Program Files (x86)/Google/Chrome/Application/chrome.exe",
                    os.path.expanduser("~/AppData/Local/Google/Chrome/Application/chrome.exe"),
                ]
                for path in possible_paths:
                    if os.path.exists(path):
                        browser_binary = path
                        break
            
            resolved_config = browser_config or BrowserConfig(
                browser_binary_path=browser_binary
            )

    _active_browser = Browser(config=resolved_config)

    _active_context = await _active_browser.new_context(
        config=context_config or BrowserContextConfig(highlight_elements=True)
    )
    
    page = await _active_context.get_agent_current_page()
    await page.goto("https://www.google.com")
    
    return _active_context
