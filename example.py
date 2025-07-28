#!/usr/bin/env python
"""
Browser-use-tool main script for testing.

This script provides a simple interface to test the browser agent.
"""
import uuid
import asyncio
import sys
import os
import logging
from browser_use import Browser, BrowserConfig
from browser_use.context import BrowserContext, BrowserContextConfig
from agents.browser_agent.agent import BrowserAgent

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler()],
)

logger = logging.getLogger(__name__)


async def main(goal: str):

    logger.info("Initializing browser...")
    chrome_path = "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe"
    # wss_url = "ws://localhost:9323/2bbd6505d20815f6797641df75327bc1"
    config = BrowserConfig(
        browser_binary_path=chrome_path, _force_keep_browser_alice=True
    )
    context_config = BrowserContextConfig(highlight_elements=True)
    browser = Browser(config=config)
    browser_context = await browser.new_context(config=context_config)

    try:
        logger.info(f"Initializing browser agent with session ID: 555")
        global active_browser_agent
        active_browser_agent = BrowserAgent(
            session_id="555",
            browser_context=browser_context,
        )

        final_state = await active_browser_agent.run(
            goal=goal, prompt="Complete this goal, and verify"
        )

        print("\n" + "=" * 50)
        print("TASK EXECUTION COMPLETE")
        print(f"Tokens: {final_state['token_usage'].__str__()}")

    except Exception as e:
        logger.error(f"Error running browser agent: {e}")
        import traceback

        traceback.print_exc()


TASK = """
go to the whatsapp web and send message to \'meta ai\'
with your introduction.
"""
# TASK = """
# search who is danish bhai on google and let me know.
# """
# TASK = """Go to the https://en.wikipedia.org/wiki/Health and find the see also section contet."""
# TASK = "go to the linkedin jobs, filter with easy apply and apply for 1 software engineer job."

active_browser_agent = None

if __name__ == "__main__":
    try:
        asyncio.run(main(goal=TASK))

    except KeyboardInterrupt:
        print("\n\n⚠️  Process interrupted by user...\n")
        print(
            "Token usage :",
            (
                active_browser_agent.token_tracker.get_usage()
                if active_browser_agent
                else "No token tracker available"
            ),
        )

    except Exception as e:
        logger.error(f"Error in main execution: {e}")
        print(
            "Token usage :",
            (
                active_browser_agent.token_tracker.get_usage()
                if active_browser_agent
                else "No token tracker available"
            ),
        )
        import traceback

        traceback.print_exc()
