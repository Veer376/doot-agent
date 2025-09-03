from dataclasses import dataclass
from langgraph.graph.message import add_messages
from typing import TypedDict, Annotated, Literal, Callable
from browser_use.context import BrowserContext
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
from ..llm import MessageBlueprintBase, GeminiMessage
from .utils import error_handler

# FIXME: change to BaseModel for consistency.
class AgentState(TypedDict):
    messages: Annotated[list[BaseMessage], add_messages]
    task: str
    step: int
    consecutive_failures: list[str]
    last_actions: list[str]
    reserved_tools: list[str]

@dataclass
class AgentContext:
    thread_id: str
    browser_context: BrowserContext
    max_consecutive_failures: int = 2
    llm: Literal["gemini", "langchain"] = "gemini"


class MessageBlueprint(MessageBlueprintBase, BaseModel):
    """Contains the messages and tools to be used in the next step of the agent's reasoning."""

    system_message: str = Field(default="No system message provided. Exit immediately.")
    
    ai_message: AIMessage | None = None
    tool_messages: list[ToolMessage] = Field(default_factory=list)

    active_tools: list[Callable] = Field(default_factory=list)

    task: str = Field(default="No task provided. Exit immediately.")

    browser_state_text: str | None = None
    browser_state_image: str | None = None

    dynamic_messages: str | None = None

    def __call__(self, target: Literal["gemini", "langchain"]):
        if target == "gemini":
            return self.to_gemini()
        elif target == "langchain":
            return self.to_langchain()
        else:
            raise ValueError(f"Unknown target: {target}")
    
    @error_handler  
    def to_gemini_format(self) -> tuple[str, list[types.Content], list[Callable]]:
        """Convert the message plan to Gemini API format."""
        # The Gemini accepts the role "user" before the "model" role.
        contents = []

        # BROWSER STATE, TASK AND DYNAMIC INSTRUCTIONS
        user_parts = []

        if self.task:
            user_parts.append(types.Part(text=f"Task: {self.task}"))
            
        if self.browser_state_image:
            image_bytes = base64.b64decode(self.browser_state_image)
            user_parts.append(types.Part(
                inline_data=types.Blob(mime_type="image/jpeg", data=image_bytes)
            ))
        
        if self.browser_state_text:
            user_parts.append(types.Part(text=f"Browser: {self.browser_state_text}"))

        if self.dynamic_messages:
            user_parts.append(types.Part(text=self.dynamic_messages))
            
        # FUNCTION RESPONSES
        function_parts = []
        
        for tool_msg in self.tool_messages:
            tool_msg: ToolMessage
            
            if not hasattr(tool_msg, "name") or not hasattr(tool_msg, "tool_call_id"):
                raise ValueError("Tool message is invalid. messages_builder/types/85")
            
            function_parts.append(
                types.Part(
                    function_response=types.FunctionResponse(
                        id=tool_msg.tool_call_id,
                        name=tool_msg.name,
                        response=dict(getattr(tool_msg, "artifact", {"result": tool_msg.content})) # artifact is of Any.
                    )
                )
            )
            
             
        # CHAIN OF THOUGHT
        
        ai_message = self.ai_message
        ai_message: GeminiMessage
        
        model_parts: list[types.Part] = []

        parts: types.PartDict = ai_message.parts if hasattr(ai_message, "parts") else []
   
        for part in parts:
            part: types.PartDict
            if "thought" in part:
                thought = part["text"]
                continue # NOTE: skipping the thought for saving tokens. OR we could have just included all the parts.
            else:
                model_parts.append(types.Part(**part))

        if user_parts:
            contents.append(types.Content(role="user", parts=user_parts))
            
        if model_parts:    
            contents.append(types.Content(role="model", parts=model_parts))
        
        if function_parts:
            contents.append(types.Content(role="user", parts=function_parts))
        
        
        return self.system_message, contents, self.active_tools
    
    @error_handler
    def to_langchain_format(self) -> tuple[list[BaseMessage], list[Callable]]:
        """Convert the message plan to LangChain format."""

        contents = []
        ai_message = self.ai_message
        ai_message: AIMessage
        
        content = ai_message.content if hasattr(ai_message, "content") else ""
        tool_calls = getattr(ai_message, "tool_calls", []) or []
                
        # SYSTEM MESSAGE
        contents.append(SystemMessage(content=self.system_message))
        
        
        # CHAIN OF THOUGHT
        
        # Human Message  
        parts = []
        
        if self.browser_state_text:
            parts.append({
                "type": "text",
                "text": f"{self.browser_state_text}",  # FIXME: add the tabs.
            })

        if self.browser_state_image:
            parts.append({
                "type": "image_url",
                "image_url": { "url": f"data:image/jpeg;base64,{self.browser_state_image}" },
            })

        if self.task:
            parts.append({
                "type": "text",
                "text": f"Goal: {self.task}",
            })

        if self.dynamic_messages:
            parts.append({
                "type": "text",
                "text": self.dynamic_messages,
            })


        contents.append(HumanMessage(content=parts))
        
        # Reasoning and tool calls
        contents.append(AIMessage(content=content if content else "Tool calls",tool_calls=tool_calls))  
              
        # Tool Messages
        for tool_message in self.tool_messages:
            tool_message: ToolMessage
            contents.append(tool_message)

        return contents, self.active_tools
