"""Playwright Manager - manages Playwright browser contexts via CDP"""
from playwright.async_api import async_playwright, Browser, BrowserContext
from typing import Optional


class PlaywrightManager:
    """Manages Playwright browser contexts via CDP"""
    
    def __init__(self):
        self.playwright = None
        self.browsers: dict[str, Browser] = {}
        self.contexts: dict[str, BrowserContext] = {}
    
    async def start(self):
        """Initialize Playwright"""
        self.playwright = await async_playwright().start()
        print("✓ Playwright initialized")
    
    async def stop(self):
        """Cleanup Playwright"""
        # Close all contexts
        for context in self.contexts.values():
            try:
                await context.close()
            except Exception as e:
                print(f"⚠️ Error closing context: {e}")
        
        # Close all browsers
        for browser in self.browsers.values():
            try:
                await browser.close()
            except Exception as e:
                print(f"⚠️ Error closing browser: {e}")
        
        if self.playwright:
            await self.playwright.stop()
        
        print("✓ Playwright stopped")
    
    async def connect_to_browser(self, session_id: str, cdp_url: str) -> BrowserContext:
        """Connect to browser via CDP and create context"""
        try:
            # Connect to browser
            browser = await self.playwright.chromium.connect_over_cdp(cdp_url)
            self.browsers[session_id] = browser
            
            # Create new context or use existing
            if browser.contexts:
                context = browser.contexts[0]
            else:
                context = await browser.new_context(
                    viewport={"width": 1280, "height": 720},
                    user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                )
            
            self.contexts[session_id] = context
            print(f"✓ Connected to browser for session {session_id}")
            return context
        
        except Exception as e:
            raise Exception(f"Failed to connect to browser: {str(e)}")
    
    async def get_context(self, session_id: str) -> Optional[BrowserContext]:
        """Get existing context"""
        return self.contexts.get(session_id)
    
    async def close_session(self, session_id: str):
        """Close context and browser for session"""
        if session_id in self.contexts:
            try:
                await self.contexts[session_id].close()
                del self.contexts[session_id]
                print(f"✓ Closed context for session {session_id}")
            except Exception as e:
                print(f"⚠️ Error closing context for {session_id}: {e}")
        
        if session_id in self.browsers:
            try:
                await self.browsers[session_id].close()
                del self.browsers[session_id]
                print(f"✓ Closed browser for session {session_id}")
            except Exception as e:
                print(f"⚠️ Error closing browser for {session_id}: {e}")
    
    def get_active_sessions(self) -> list[str]:
        """Get list of active session IDs"""
        return list(self.contexts.keys())
