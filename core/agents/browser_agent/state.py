from dataclasses import dataclass
from langgraph.graph.message import add_messages
from typing import TypedDict, Annotated
from langchain_core.messages import (
    BaseMessage,
)

@dataclass
class Snippet:
    type: str
    message: str

class BrowserSnapshot(TypedDict):
    url: str | None  # current url
    screenshot: str | None  # base64 encoded screenshot of current page
    dom_text: str | None  # text content of the current page

class AgentState(TypedDict, total=False):
    messages: Annotated[list[BaseMessage], add_messages] 
    step: int
    reserved_tools: list[str]
    scratchpad: list[Snippet]

    browser_snapshot: BrowserSnapshot

class AgentContext(TypedDict, total=False):
    user_id: str | None