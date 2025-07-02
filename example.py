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
from langgraph.types import Command

async def main(task, use_debug_chrome):
    
    browser = await initialize_browser(use_debug_chrome=use_debug_chrome)
    
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
            "recursion_limit": 50,
            "configurable" : {
                "thread_id": str(uuid.uuid4()),
            }
        }
        
        async for chunk in agent.astream(initial_state, config=config, stream_mode="values"):
               
            interrupted_checkpoint = None
            if "__interrupt__" in chunk:
                print("INTERRUPTED!")
                print(f"Agent: {chunk['__interrupt__']}")
                interrupted_checkpoint = chunk
                break
            
            else : print(chunk["messages"][-1].pretty_print())
            
        if interrupted_checkpoint:

            interrupted2 = None
            async for chunk in agent.astream(Command(resume=input("USER: ")), config=config, stream_mode="values"):
                    
                if "__interrupt__" in chunk:
                    print("INTERRUPTED AGAIN!")
                    print(f"Agent: {chunk['__interrupt__']}")
                    break
                else : print(chunk["messages"][-1].pretty_print())
                
            interrupted2 = chunk

            if interrupted2:
                user_input = input("USER: ")
                async for chunk in agent.astream(Command(resume=user_input), config=config, stream_mode="values"):
                    if "__interrupt__" in chunk:
                        print("INTERRUPTED AGAIN!")
                        print(f"Agent: {chunk['__interrupt__']}")
                        break
                    else : print(chunk["messages"][-1].pretty_print())

    except Exception as e:
        print(f"An error occurred: {e}")
    finally:
        await browser.close()



USE_DEBUG_CHROME = True
TASK = "go to the url https://web.whatsapp.com and send message to 'abhishek' with your introduction as a browser automation. You have to ask abhishek if he is free to go on 'nadhi' today, ask reason if says no"
asyncio.run(main(task=TASK, use_debug_chrome=USE_DEBUG_CHROME))