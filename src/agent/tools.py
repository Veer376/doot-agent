import base64
from langchain_core.tools import tool
from typing import List, Dict, Any
from google.genai import types
from langgraph.prebuilt import InjectedState
from .utils import correct_coordinates
from ..browser.browser_manager import get_browser
from .schema import *
from langgraph.types import interrupt
import asyncio
from google import genai
import os

@tool(
    "navigate_to_url", 
    args_schema=UrlSchema, 
    description="Use this tool to navigate to a specific website URL."
)
async def navigate_to_url(url: str) -> str:
    browser = await get_browser()
    result = await browser.navigate(url)
    return result["message"]


class BoundingBox(BaseModel):
    ymin: float
    xmin: float
    ymax: float
    xmax: float
    

@tool(
    "click_element", 
    description="Use this tool to click on an element in the current page."
)
async def click_element(label: str) -> str:
    
    browser = await get_browser()
    screenshot = await browser.screenshot_bytes()
    screenshot = base64.b64encode(screenshot).decode('utf-8')
        
    image_part = genai.types.Part(
        inline_data=genai.types.Blob(
            mime_type="image/png",
            data=screenshot
        )
    )
    
    response = genai.Client(api_key=os.getenv("GENAI_API_KEY")).models.generate_content(
        model="gemini-2.5-flash",
        contents=[image_part, f"See the image, find the {label} clickable element and return its bounding box coordinates in the format: [ymin, xmin, ymax, xmax]. The coordinates should be normalized to 0-1000 scale."],
        config=types.GenerateContentConfig(
            response_mime_type="application/json",
            response_schema=BoundingBox,
            system_instruction="""
            You are expert in computer vision and spatial understanding.
            You are provided with a label/element to click on a webpage like button, link, input field etc.
            You task is to identify and return a bounding box coordinates of the element in the screenshot.
            The coordinates should be normalized to 0-1000 scale.
            """
        )
    )
    
    import json
    content = response.text
    bbox_data = json.loads(content)
    ymin, xmin, ymax, xmax = bbox_data["ymin"], bbox_data["xmin"], bbox_data["ymax"], bbox_data["xmax"]
    x =  (xmin + xmax) / 2
    y = (ymin + ymax) / 2
    
    x,y = correct_coordinates(x,y)
    
    await browser.show_pointer(x=x, y=y)
    await browser.page.wait_for_timeout(10000)
    await browser.hide_pointer()

    result = await browser.click(x=x, y=y)
    return result["message"]
     
    
@tool(
    "type_text",
    args_schema=TypeTextSchema,
    description="use this tool to type text in the input field."
)
async def type_text(text: str, label: str) -> str:
    browser = await get_browser()
    result = await browser.type_text(text=text, label=label)
    return result["message"]


@tool(
    "press_keys", 
    args_schema=PressKeysSchema, 
    description="Use this tool to press keys on the keyboard e.g( 'Enter', 'Backspace' etc."
)
async def press_keys(keys: list[str]) -> str:
    browser = await get_browser()
    result = await browser.press_keys(keys=keys)
    return result["message"]


@tool(
    "go_back", 
    description="Use this tool to go back to the previous page in the browser history."
)
async def go_back() -> str:
    browser = await get_browser()
    result = await browser.go_back()
    return result["message"]


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





tools = [
    # navigate_to_url,
    click_element,
    type_text,
    press_keys,
    go_back,
    # human_interaction,
    wait
]