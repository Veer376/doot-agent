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
from agents.browser_agent.agent import BrowserAgent

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler()
    ]
)

logger = logging.getLogger(__name__)

async def main(task: str):

    # task = sys.argv[1] if len(sys.argv) > 1 else "Search for 'browser automation' on Bing and get the top results"
    
    # Initialize browser
    logger.info("Initializing browser...")
    chrome_path = "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe"
    local_cdp_url = "ws://127.0.0.1:9222"
    config = BrowserConfig(browser_binary_path=chrome_path)
    browser = Browser(config=config)
    browser_context = await browser.new_context()
    
    try:

        # Initialize the browser agent
        logger.info(f"Initializing browser agent with session ID: 555")
        browser_agent = BrowserAgent(
            session_id="555",
            browser_context=browser_context,
        )
        
        
        # Run the agent with the given task
        logger.info(f"Running agent with task: {task}")
        print("\n" + "="*50)
        print(f"EXECUTING TASK: {task}")
        print("="*50 + "\n")
        
        await browser_agent.run(task)
        
        print("\n" + "="*50)
        print("TASK EXECUTION COMPLETE")
        print("="*50 + "\n")
        
    except Exception as e:
        logger.error(f"Error running browser agent: {e}")
        import traceback
        traceback.print_exc()


# TASK = """
# go to the whatsapp web and send message to abhishek with your introduction as the browser automation agent developed by Aryaveer.
# """
TASK = """
go to the whatsapp web and send message to abhishek with your 
introduction.
"""
if __name__ == "__main__":
    try:
        asyncio.run(main(task = TASK))
    except KeyboardInterrupt:
        logger.info("Script terminated by user")
    except Exception as e:
        logger.error(f"Error in main execution: {e}")
        import traceback
        traceback.print_exc()