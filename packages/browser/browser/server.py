"""
Playwright browser server that launches Chromium with CDP endpoint
The browser will display in Docker's virtual screen visible via noVNC
"""
import asyncio
import signal
import sys
from playwright.async_api import async_playwright


browser = None


async def start_browser():
    """Launch Chromium with CDP debugging enabled"""
    global browser
    
    print("🚀 Starting Playwright browser with CDP...")
    
    async with async_playwright() as p:
        # Launch Chromium with CDP debugging on port 9222 (bound to localhost)
        # The socat forwarder will expose this on 0.0.0.0:9223
        browser = await p.chromium.launch(
            headless=False,
            args=[
                "--remote-debugging-port=9222",
                "--start-maximized",
                "--kiosk",
                "--no-first-run",
                "--no-default-browser-check",
                "--disable-background-networking",
                "--disable-background-timer-throttling",
                "--disable-backgrounding-occluded-windows",
                "--disable-breakpad",
                "--disable-client-side-phishing-detection",
                "--disable-component-extensions-with-background-pages",
                "--disable-default-apps",
                "--disable-dev-shm-usage",
                "--disable-extensions",
                "--disable-features=TranslateUI",
                "--disable-hang-monitor",
                "--disable-ipc-flooding-protection",
                "--disable-popup-blocking",
                "--disable-prompt-on-repost",
                "--disable-renderer-backgrounding",
                "--disable-sync",
                "--force-color-profile=srgb",
                "--metrics-recording-only",
                "--no-sandbox",
                "--password-store=basic",
                "--use-mock-keychain",
                "--enable-automation",
            ]
        )
        
        print(f"✅ Browser launched! CDP endpoint: http://localhost:9222")
        print(f"📡 External CDP endpoint (via socat): http://0.0.0.0:9223")
        print(f"🖥️  Browser visible at: http://localhost:6080 (noVNC)")
        
        # Keep the browser running
        try:
            while True:
                await asyncio.sleep(1)
        except asyncio.CancelledError:
            print("🛑 Shutting down browser...")
            if browser:
                await browser.close()


def signal_handler(signum, frame):
    """Handle shutdown signals gracefully"""
    print(f"\n⚠️  Received signal {signum}, shutting down...")
    sys.exit(0)


if __name__ == "__main__":
    # Register signal handlers
    signal.signal(signal.SIGTERM, signal_handler)
    signal.signal(signal.SIGINT, signal_handler)
    
    try:
        asyncio.run(start_browser())
    except KeyboardInterrupt:
        print("\n👋 Browser server stopped")
    except Exception as e:
        print(f"❌ Error: {e}")
        sys.exit(1)
