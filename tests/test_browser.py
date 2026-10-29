#!/usr/bin/env python3
"""
Simple test to verify Playwright WebSocket connection.
Test: hi
"""
import asyncio
from playwright.async_api import async_playwright

WSS_URL = "ws://localhost:3500"  # From logs: Listening on ws://0.0.0.0:3500/


async def test_connection():
    async with async_playwright() as p:
        browser = await p.chromium.connect(WSS_URL)
        print("✅ Connected to Playwright server")

        context = await browser.new_context()
        page = await context.new_page()
        await page.goto("https://example.com")
        title = await page.title()
        print(f"✅ Page loaded: {title}")

        await context.close()
        await browser.close()
        print("✅ Test passed")


if __name__ == "__main__":
    asyncio.run(test_connection())
