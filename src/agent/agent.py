from typing import Annotated, List, Dict, Any, Literal, Optional, Union
from pydantic import BaseModel, Field
from langchain_core.messages import SystemMessage, AIMessage, ToolMessage
from langchain_core.messages.human import HumanMessage
from typing_extensions import TypedDict
from langgraph.types import interrupt, Command, Send
from langgraph.checkpoint.memory import InMemorySaver
import uuid
import os
import base64
from langchain_core.tools import tool
from langgraph.graph import StateGraph, START, END
from langgraph.prebuilt import ToolNode
from .utils import get_model, SYSTEM_MESSAGE
from .tools import tools
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.errors import NodeInterrupt
from .schema import *

llm = get_model()


browser_action_router = ToolNode(
    tools,
    name="browser_action_router"
)


x=0
async def browser_supervisor(state: AgentState):
    """Supervisor agent that manages browser actions based on user goals."""
    print("supervisor agent...")
    
    multimodal_content = [
        {"type": "text", "text": f"Goal: {state['goal']}"},
        {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{state['browser_state']['screenshot']}"}},
    ]
    
    
    folder = "screenshots"
    if not os.path.exists(folder):
        os.makedirs(folder)
        
    global x
    filename = f"screenshot_{x}.png"
    x += 1
    filepath = os.path.join(folder, filename)

    image_data = base64.b64decode(state['browser_state']['screenshot'])
    with open(filepath, "wb") as f:
        f.write(image_data)
        
        
    response = await llm.bind_tools(tools).ainvoke([
        SystemMessage(content=SYSTEM_MESSAGE),
        HumanMessage(content=multimodal_content)
    ])
    return {"messages": [response]}



builder = StateGraph(AgentState)
builder.add_node("browser_supervisor", browser_supervisor)
builder.add_node("browser_action_router", browser_action_router)
builder.add_edge(START, "browser_supervisor")
builder.add_conditional_edges(
    "browser_supervisor",
    lambda state: "browser_action_router" if getattr(state["messages"][-1], "tool_calls", None) else END
)


checkpointer = InMemorySaver()
agent = builder.compile(checkpointer=checkpointer)