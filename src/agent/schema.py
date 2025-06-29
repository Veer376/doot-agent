from pydantic import BaseModel, Field
from typing import Optional, List, TypedDict, Annotated
from langgraph.graph.message import add_messages


class BrowserState(BaseModel):
    """Current state of the browser"""
    screenshot: str = Field(..., description="Base64 encoded screenshot of the current browser state")
    url: str = ""
    viewport_width: int = 1280
    viewport_height: int = 800
    page_title: Optional[str] = None
    
class AgentState(TypedDict):
    """State maintained by the supervisor agent"""
    messages: Annotated[list[dict], add_messages]
    goal: str
    browser_state: BrowserState
    execution_history: List[str]  # History of actions performed

class UrlSchema(BaseModel):
    url: str = Field(..., description="The website URL to navigate to")

class ClickSchema(BaseModel):
    label: str = Field(..., description="element to click on")
    x: float = Field(..., description="X coordinate of the element to click on")
    y: float = Field(..., description="Y coordinate of the element to click on")
    
class TypeTextSchema(BaseModel):
    text: str = Field(..., description="Text to type into the input field")
    label: str = Field(..., description="Label of the input field to type into.")

class PressKeysSchema(BaseModel):
    keys: list[str] = Field(..., description="List of keys to press on the keyboard. For example: ['Enter', 'a', 'b', 'c']")

class InteractionSchema(BaseModel):
    query: str = Field(..., description="The query or question to ask the user for input or clarification.")
  
class WaitSchema(BaseModel):
    seconds: int = Field(..., description="Number of seconds to wait before proceeding with the next action.")
 
class ClickStateSchema(BaseModel):
    state: AgentState
    label: str = Field(..., description="Label of the element to click on")