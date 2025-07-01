#!/usr/bin/env python
"""
Browser-use-tool main script for testing.

This script provides a simple interface to test the browser agent.
"""
import uuid
import asyncio
import sys
import os
import base64
from typing import Dict, Any
from src.browser import initialize_browser
from langgraph.errors import NodeInterrupt
from src.agent.agent import agent

async def main(task):
    
    browser = await initialize_browser(viewport_width=1024, viewport_height=768)
    
    try: 
        await browser.navigate("https://www.bing.com")
        print("Browser initialized and navigated to Bing.")
        screenshot = await browser.screenshot_bytes()
        screenshot_base64 = base64.b64encode(screenshot).decode('utf-8')
        
        initial_state = {
            "user_id": "user_123",
            "session_id": str(uuid.uuid4()),
            "messages": [{"role": "user", "content": task}],
            "execution_state": {
                "task": task,
                "history": [],
                "errors": [],
                "consecutive_failures": 0,
                "status": "pending",
            },
            "browser_state": {
                "page_title": "Bing",
                "url": "https://www.bing.com",
                "dom_structure": "",
                "viewport_width": browser.viewport_width,
                "viewport_height": browser.viewport_height,
                "screenshots": [screenshot_base64]
            }
        }
        
        config = {
            "recursion_limit": 10,
            "configurable" : {
                "thread_id": str(uuid.uuid4()),
            }
        }
        
        agent.update_state(config=config, values=initial_state)
        
        from rich.markdown import Markdown
        from rich.console import Console
        
        async for chunk in agent.astream({"messages": []}, config=config, stream_mode="values"):
            
                print(chunk["messages"][-1].pretty_print())
        

    except Exception as e:
        print(f"An error occurred: {e}")
    finally:
        await browser.close()


asyncio.run(main(task = "book a movie ticket for Animal for tomorrow at 7pm greater noida grand venice mall"))