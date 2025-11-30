"""
Browser Session Registry.

Manages browser contexts keyed by session/user ID.
For now uses in-memory storage; can be extended to Redis for persistence.

Usage:
    # Store a context
    await browser_registry.create_session("user_123")
    
    # Get a context
    context = await browser_registry.get_session("user_123")
    
    # Remove a context
    await browser_registry.remove_session("user_123")
"""

from __future__ import annotations

import asyncio
import logging
import os
from typing import Dict, Optional

from orbit_core.browser_use.browser import Browser, BrowserConfig
from orbit_core.browser_use.context import BrowserContext, BrowserContextConfig

logger = logging.getLogger("agent_platform")


class BrowserSessionRegistry:
    """
    Registry for managing browser sessions.
    
    Each session is keyed by a session_id (typically user_id).
    Supports single browser with multiple contexts pattern.
    """
    
    def __init__(self):
        self._browser: Optional[Browser] = None
        self._contexts: Dict[str, BrowserContext] = {}
        self._lock = asyncio.Lock()
        self._wss_url: Optional[str] = None  # Explicit WSS URL if set
    
    def set_wss_url(self, url: str) -> None:
        """Set the browser WSS URL explicitly."""
        self._wss_url = url
        logger.info(f"Browser WSS URL set to: {url}")
    
    def _get_wss_url(self) -> Optional[str]:
        """Get browser WSS URL from explicit setting or environment."""
        return self._wss_url or os.environ.get("BROWSER_WSS_URL")
    
    async def _ensure_browser(self) -> Browser:
        """Ensure we have a browser instance."""
        if self._browser is not None:
            return self._browser
        
        wss_url = self._get_wss_url()
        
        if wss_url:
            logger.info(f"Connecting to remote browser at: {wss_url}")
            config = BrowserConfig(wss_url=wss_url)
        else:
            # Fallback: use built-in browser (may not work on Windows in FastAPI)
            logger.warning("No BROWSER_WSS_URL set, using built-in browser")
            config = BrowserConfig()
        
        self._browser = Browser(config=config)
        return self._browser
    
    async def create_session(
        self,
        session_id: str,
        initial_url: str = "https://www.google.com",
        config: Optional[BrowserContextConfig] = None,
    ) -> BrowserContext:
        """
        Create a new browser session for the given session_id.
        
        If a session already exists, returns the existing one.
        """
        async with self._lock:
            # Return existing if present
            if session_id in self._contexts:
                logger.info(f"Session {session_id} already exists, returning existing context")
                return self._contexts[session_id]
            
            # Ensure browser is running
            browser = await self._ensure_browser()
            
            # Create new context
            context_config = config or BrowserContextConfig(
                window_width=1280,
                window_height=720,
                highlight_elements=False,
            )
            
            context = await browser.new_context(config=context_config)
            
            # Navigate to initial page
            page = await context.get_agent_current_page()
            await page.goto(initial_url)
            
            # Store in registry
            self._contexts[session_id] = context
            logger.info(f"Created browser session: {session_id}")
            
            return context
    
    async def get_session(self, session_id: str) -> Optional[BrowserContext]:
        """Get an existing browser session by ID."""
        return self._contexts.get(session_id)
    
    async def remove_session(self, session_id: str) -> bool:
        """Remove and close a browser session."""
        async with self._lock:
            if session_id not in self._contexts:
                return False
            
            context = self._contexts.pop(session_id)
            # Context cleanup is handled by the browser
            logger.info(f"Removed browser session: {session_id}")
            return True
    
    def list_sessions(self) -> list[str]:
        """List all active session IDs."""
        return list(self._contexts.keys())
    
    async def close_all(self):
        """Close all sessions and the browser."""
        async with self._lock:
            self._contexts.clear()
            
            if self._browser:
                await self._browser.close()
                self._browser = None
            
            logger.info("Closed all browser sessions")


# Global singleton instance
browser_registry = BrowserSessionRegistry()
