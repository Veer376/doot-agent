"""
Module for managing the global browser instance.
This allows sharing a single browser instance across different parts of the application.
"""
from typing import Optional
from .browser import Browser

# Global browser instance
_browser_instance: Optional[Browser] = None

async def initialize_browser(use_debug_chrome: bool = False
) -> Browser:
    
    global _browser_instance
    if _browser_instance is None:
        _browser_instance = Browser(use_debug_chrome=use_debug_chrome)
        await _browser_instance.initialize()
    return _browser_instance

async def get_browser(viewport_width=1280, viewport_height=800) -> Browser:
    
    global _browser_instance
    if _browser_instance is None:
        await initialize_browser(viewport_width, viewport_height)
    return _browser_instance

async def close_browser():
    
    global _browser_instance
    if _browser_instance is not None:
        await _browser_instance.close()
        _browser_instance = None