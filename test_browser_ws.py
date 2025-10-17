"""Test WebSocket connection to the browser"""
import asyncio
from playwright.async_api import async_playwright

async def test_browser_connection():
    # Try connecting to the browser WebSocket endpoint
    ws_url = "ws://localhost:3500/"
    
    print(f"Attempting to connect to: {ws_url}")
    
    try:
        async with async_playwright() as p:
            browser = await p.chromium.connect(ws_url)
            print("✅ Successfully connected to browser!")
            
            # Create a page to verify it works
            page = await browser.new_page()
            await page.goto("https://example.com")
            title = await page.title()
            print(f"✅ Page loaded successfully. Title: {title}")
            
            await page.close()
            await browser.close()
            print("✅ Test completed successfully!")
            return True
            
    except Exception as e:
        print(f"❌ Connection failed: {e}")
        return False

if __name__ == "__main__":
    success = asyncio.run(test_browser_connection())
    exit(0 if success else 1)
