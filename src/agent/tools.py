import base64
from langchain_core.tools import tool
from typing import List, Dict, Any
from google.genai import types
from langgraph.prebuilt import InjectedState
from .utils import correct_coordinates
from ..browser import get_browser
from .schema import *
from langgraph.types import interrupt
import asyncio
from google import genai
import os

@tool(
    "navigate_to_url", 
    description="Use this tool to navigate to a specific website URL."
)
async def navigate_to_url(url: str, state: Annotated[dict, InjectedState]) -> str:
    browser = await get_browser()
    result = await browser.navigate(url)
    
    if not result.success:
        state['execution_state']['consecutive_failures'] += 1
        state['execution_state']['errors'].append(f"Failed to navigate to {url}. Error: {result.message}")
    else :
        state['execution_state']['history'].append(f"Navigated to {url}")
        state['browser_state']['url'] = url
        # state['browser_state']['dom_structure'] = await browser.get_dom_structure()
    return result.message


@tool(
    "click",
    description="Use this tool to click on an element on the browser page by providing its label. "
)
async def click(label: str, description: str, state: Annotated[dict, InjectedState]) -> str:
    
    screenshot = state["browser_state"]["screenshots"][-1]  
    
    image_part = genai.types.Part(
        inline_data=genai.types.Blob(
            mime_type="image/png",
            data=screenshot
        )
    )
    # First handle the label using the locator() function, then only use the genai API.
    response = genai.Client(api_key=os.getenv("GENAI_API_KEY")).models.generate_content(
        model="gemini-2.5-flash",
        contents=[image_part, f"Bounding box for label: '{label}' with description '{description}'. It should be in the format: [ymin, xmin, ymax, xmax] normalized to 0-1000."],
        config=types.GenerateContentConfig(
            response_mime_type="application/json",
            system_instruction="""
            You are a helpful assistant, expert in computer vision and spatial understanding.
            You will be provided with a screenshot of a web page and a label describing a clickable element on that page like button, dropdown, clickable text, etc.
            Your task is to identify and return a most appropriate bounding box coordinates of the clickable element on the browser matching the label in the screenshot.
            
            **Follow these guidelines:**
            1. Elements can be a button, link, input field, or any other clickable element.
            2. Generate correct bounding box coordinates for the element.
            3. If multiple elements match the description, return the most appropriate one.
            
            The bounding box coordinates should be in the format: [ymin, xmin, ymax, xmax].
            The coordinates should be normalized to 0-1000 scale.
            """
        )
    )
    
    import json
    bounding_box = json.loads(response.text)
    
    print(f"INSIDE THE CLICK_ELEMENT Bounding box for {label}: {bounding_box}")
    
    y1 = int(bounding_box[0])
    x1 = int(bounding_box[1])
    y2 = int(bounding_box[2])
    x2 = int(bounding_box[3])
    
    if y1 == 0 and x1 == 0 and y2 == 0 and x2 == 0:
        return f"Failed because the LLM didn't find the coordinates of the label, Try to give the label with detail description"
    
    x =  (x1 + x2) / 2
    y = (y1 + y2) / 2

    x,y = correct_coordinates(x,y)
    
    browser = await get_browser()
    
    await browser.show_pointer_pro(x=x, y=y)
    await browser.page.wait_for_timeout(10000)
    await browser.hide_pointer()

    result = await browser.click(x=x, y=y, label=label)
    
    if not result.success:
        state['execution_state']['consecutive_failures'] += 1
        state['execution_state']['errors'].append(f"Failed to click on {label}. Error: {result.message}")
    else:
        state['execution_state']['history'].append(f"Clicked on {label}")
        
    return result.message
     
    
@tool(
    "type",
    description="use this tool to type text in the input field."
)
async def type(text: str, label: str, state: Annotated[dict, InjectedState]) -> str:
    
    browser = await get_browser()
    result = await browser.type(text=text, label=label)
    
    if not result.success:
        state['execution_state']['consecutive_failures'] += 1
        state['execution_state']['errors'].append(f"Failed to type text in {label}. Error: {result.message}")
    else:
        state['execution_state']['history'].append(f"Typed '{text}' in {label}")

    return result.message


@tool(
    "press_keys", 
    # args_schema=PressKeysSchema, 
    description="Use this tool to press keys on the keyboard e.g( 'Enter', 'Backspace' etc."
)
async def press_keys(keys: list[str], state: Annotated[dict, InjectedState]) -> str:
    browser = await get_browser()
    result = await browser.press_keys(keys=keys)
    
    if not result.success:
        state['execution_state']['consecutive_failures'] += 1
        state['execution_state']['errors'].append(f"Failed to press keys {keys}. Error: {result.message}")
    else: 
        state['execution_state']['history'].append(f"Pressed keys {keys}")
    return result.message


@tool(
    "go_back", 
    description="Use this tool to go back to the previous page in the browser history."
)
async def go_back(state: Annotated[dict, InjectedState]) -> str:
    browser = await get_browser()
    result = await browser.go_back()

    if not result.success:
        state['execution_state']['consecutive_failures'] += 1
        state['execution_state']['errors'].append(f"Failed to go back. Error: {result.message}")
    else:
        state['execution_state']['history'].append("Went back to the previous page.")

    return result.message


@tool(
    "human_interaction", 
    args_schema=InteractionSchema, 
    description="Use this tool to interact with the user if encountered any errors or need any help to proceed with the sensitive task. e.g. ('I need to login let me know your credentials', 'i have encountered mulitple errors how i should proceed') etc."
)
async def human_interaction(query: str):
    value = interrupt({"Agent": query})
    return value


@tool(
    "wait", 
    args_schema=WaitSchema, 
    description="Use this tool to wait for seconds before proceeding with the next action."
)
async def wait(seconds: int):
    await asyncio.sleep(seconds)

@tool(
    "exit",
    description="use this tool to exit the agent."
)
async def exit(reason: str, state: Annotated[dict, InjectedState]) -> str:
    state['execution_state']['status'] = "failed"
    return f"Agent exited: {reason}"


tools = [
    navigate_to_url,
    click,
    type,
    press_keys,
    go_back,
    human_interaction,
    wait,
    exit
]