"""
Test script to connect to Playwright CDP server in Docker and navigate to Google
The browser will display in Docker's virtual screen visible via noVNC
"""
import asyncio
from playwright.async_api import async_playwright
from pathlib import Path


async def test_browser_control():
    print("🔌 Connecting to Playwright CDP server in Docker...")
    
    browser = None
    
    try:
        async with async_playwright() as p:
            # Connect to the remote CDP endpoint running in Docker
            # The server launches Chromium with --remote-debugging-port=9222
            # Socat forwards 0.0.0.0:9223 -> localhost:9222 for external access
            print("📡 Connecting to CDP endpoint: http://localhost:9223")
            browser = await p.chromium.connect_over_cdp("http://localhost:9223")
            print("✅ Connected to CDP server!")
            
            # CDP connections provide default context and pages
            contexts = browser.contexts
            if contexts:
                context = contexts[0]
                print(f"📄 Using default context (found {len(contexts)} contexts)")
                pages = context.pages
                if pages:
                    page = pages[0]
                    print(f"📄 Using existing page (found {len(pages)} pages)")
                else:
                    page = await context.new_page()
                    print("📄 New page created")
            else:
                # Fallback: create new context if none exists
                context = await browser.new_context(
                    viewport={'width': 1280, 'height': 720}
                )
                page = await context.new_page()
                print("📄 New context and page created")
            
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
        if browser:
            try:
                await browser.close()
                print("✅ Browser connection closed")
            except Exception as e:
                print(f"⚠️ Error closing browser: {e}")
        
        print("✅ Cleanup complete!")


if __name__ == "__main__":
    asyncio.run(test_browser_control())
