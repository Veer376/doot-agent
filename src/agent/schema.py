from pydantic import BaseModel, Field
from typing import Optional, List, TypedDict, Annotated
from langgraph.graph.message import add_messages
from enum import Enum

class ExecutionStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    INTERRUPTED = "interrupted"
    CANCELLED = "cancelled"

class ExecutionState:
    task: str
    history: list[str]
    errors: list[str]
    consecutive_failures: int = 2
    status: ExecutionStatus
    
class PageState:
    page_title: str
    url: str
    dom_structure: str
    viewport_width: int
    viewport_height: int
    screenshots: list[str]

class AgentState(TypedDict):
    # identity state
    user_id: str
    session_id: str
    messages: Annotated[list[dict], add_messages]
    # execution state
    execution_state: ExecutionState
    # page state 
    browser_state: PageState # 'll only track the current page state


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
 