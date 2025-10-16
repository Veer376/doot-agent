from dataclasses import dataclass, field
from langgraph.graph.message import add_messages
from typing import TypedDict, Annotated, Literal, Callable
import base64
from google.genai import types
from pydantic import BaseModel, Field
from langchain_core.messages import (
    AIMessage,
    BaseMessage,
    ToolMessage,
    SystemMessage,
    HumanMessage,
)
from ..llm import MessageBlueprintBase, GeminiMessage, LLMConfig
from .utils import error_handler
from core.browser_use.browser import BrowserConfig
from core.browser_use.context import BrowserContext, BrowserContextConfig


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
    consecutive_failures: list[str]
    last_actions: list[str]
    reserved_tools: list[str]
    scratchpad: list[Snippet]

    browser_snapshot: BrowserSnapshot

class AgentContext(TypedDict, total=False):
    user_id: str | None