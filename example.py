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
            "messages": [{"role": "user", "content": task}],
            "goal": task,
            "browser_state": {
                "screenshot": screenshot_base64,
                "url": "https://www.bing.com",  # Initial URL
                "viewport_width": browser.viewport_width,
                "viewport_height": browser.viewport_height,
                "page_title": "Bing"  # Initial page title assumption
            },
            "execution_history": []
        }
        
        config = {
            "recursion_limit": 10,
            "configurable" : {
                "thread_id": str(uuid.uuid4()),
            }
        }
        
        agent.update_state(config=config, values=initial_state)
        
        for _ in range(20):
            
            async for chunk in agent.astream({"messages": []}, config=config, stream_mode="values"):
                
                if '__interrupt__' in chunk:
                    user_input = input(f"{chunk['__interrupt__']}")
                    agent.update_state(config=config, values={"messages": [{"role": "user", "content": user_input}]})
                    
                else: 
                    print(chunk["messages"][-1].pretty_print())
            
                    screenshot = await browser.screenshot_bytes()
                    screenshot_base64 = base64.b64encode(screenshot).decode('utf-8')
                    # Update just the screenshot in browser_state
                    agent.update_state(config=config, values={"browser_state": {"screenshot": screenshot_base64}})

    except Exception as e:
        print(f"An error occurred: {e}")
    finally:
        await browser.close()


asyncio.run(main(task = "book a movie ticket for Animal for tomorrow at 7pm greater noida grand venice mall"))