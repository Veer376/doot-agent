"""
Simple test - launch browser directly in Docker container
This ensures the browser uses the DISPLAY environment variable
"""
import subprocess
import time

print("🚀 Launching browser in Docker container...")

# Launch browser directly in container with DISPLAY set
cmd = [
    "docker", "exec", "-d", "browser-vnc",
    "sh", "-c",
    """
    DISPLAY=:0 python << 'PYSCRIPT'
import asyncio
from playwright.async_api import async_playwright

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)
        page = await browser.new_page()
        await page.goto("https://www.google.com")
        print("Browser opened on VNC!")
        await asyncio.sleep(300)  # 5 minutes
        await browser.close()

asyncio.run(main())
PYSCRIPT
    """
]

result = subprocess.run(cmd, capture_output=True, text=True)

if result.returncode == 0:
    print("✅ Browser launched successfully!")
    print("👉 Open http://localhost:6080 to see it")
    print("⏳ Browser will stay open for 5 minutes")
else:
    print(f"❌ Error: {result.stderr}")
