"""
Test script to connect to Playwright server in Docker and navigate to Google
The browser will display in Docker's virtual screen visible via noVNC
"""
import asyncio
from playwright.async_api import async_playwright
from pathlib import Path


async def test_browser_control():
    print("🔌 Connecting to Playwright server in Docker...")
    
    browser = None
    context = None
    
    try:
        async with async_playwright() as p:
            # Connect to the remote Playwright server running in Docker
            # Note: When connecting to run-server, browser is already launched by the server
            browser = await p.chromium.connect("ws://localhost:3500/")
            print("✅ Connected to Playwright server!")
            
            # Get or create browser context
            # The server manages the browser, we just use contexts
            contexts = browser.contexts
            if contexts:
                context = contexts[0]
                print(f"📄 Using existing context (found {len(contexts)} contexts)")
            else:
                context = await browser.new_context(
                    viewport={'width': 1280, 'height': 720}
                )
                print("📄 New context created")
            
            page = await context.new_page()
            print("📄 New page created")
            
            # Navigate to Google
            print("🌐 Navigating to https://www.google.com...")
            await page.goto("https://www.google.com", wait_until="networkidle")
            print("✅ Page loaded!")
            
            # Take a screenshot using Playwright
            screenshot_path = Path("playwright_screenshot.png")
            await page.screenshot(path=str(screenshot_path), full_page=False)
            print(f"📸 Screenshot saved to: {screenshot_path.absolute()}")
            
            # Get page title for verification
            title = await page.title()
            print(f"📑 Page title: {title}")
            
            print("\n" + "="*60)
            print("🎉 SUCCESS! Browser connected and page loaded")
            print("👉 Open http://localhost:6080 in your browser")
            print("👉 You should see Google.com in the noVNC window!")
            print(f"📸 Check the screenshot: {screenshot_path.absolute()}")
            print("="*60 + "\n")
            
            # Keep browser alive for 5 minutes so you can test noVNC
            print("⏳ Keeping browser open for 5 minutes...")
            print("   (Press Ctrl+C to exit early)")
            
            try:
                await asyncio.sleep(300)  # 5 minutes
            except KeyboardInterrupt:
                print("\n👋 Closing browser...")
            
    finally:
        # Ensure proper cleanup
        if context:
            try:
                await context.close()
                print("✅ Context closed")
            except Exception as e:
                print(f"⚠️ Error closing context: {e}")
        
        if browser:
            try:
                await browser.close()
                print("✅ Browser closed")
            except Exception as e:
                print(f"⚠️ Error closing browser: {e}")
        
        print("✅ Cleanup complete!")


if __name__ == "__main__":
    asyncio.run(test_browser_control())
