import sys
from pathlib import Path

repo_root = (
    Path(__file__).resolve().parents[2]
)  # go up from core/agents/<this file> to repo root
if str(repo_root) not in sys.path:
    sys.path.insert(0, str(repo_root))


from core.clients.redis_client import redis_client
import asyncio
import uuid
import time
import json
from typing import Literal, Optional
from langchain_core.messages import (
    SystemMessage,
    AIMessage,
    ToolMessage,
    HumanMessage,
    BaseMessage
)
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import START, END, StateGraph
from langgraph.types import Command
from langgraph.runtime import Runtime
from dataclasses import dataclass, field
from langgraph.graph.message import add_messages
from typing import TypedDict, Annotated, Literal, Callable
from core.browser_use.context import BrowserContext
import base64
from langgraph.config import get_stream_writer
from google.genai import types
from pydantic import BaseModel, Field
from langchain_core.messages import (
    AIMessage,
    AIMessageChunk,
    BaseMessage,
    ToolMessage,
    SystemMessage,
    HumanMessage,
)
from google import genai
from google.genai import types
import json
from core.clients.supabase_client import DBConnection
from langchain.chat_models import init_chat_model
from core.clients.langgraph_checkpointer import checkpointer

class State(TypedDict):
    messages: Annotated[list[dict], add_messages]


async def model_node(state: State):
    
    model = init_chat_model("google_genai:gemini-2.0-flash", temperature=0.7)
    
    response = await model.ainvoke(state["messages"])
    # response = AIMessage(content="Hello from model node")
    
    return {"messages": [response]}


graph = (
    StateGraph(State)
    .add_node(model_node)
    .add_edge(START, "model_node")
    .add_edge("model_node", END)
    .compile(checkpointer=checkpointer)
)


async def process_run(thread_id: str, run_id: str, body: any):
    """Process a run and stream the results via Redis"""

    message_id = str(uuid.uuid4())
    assistant_id = getattr(body, "assistant_id", None)
    stream_mode = getattr(body, "stream_mode", None)
    input = getattr(body, "input", {}) or body.get("input", {})
    if not input: 
        raise ValueError("Input cannot be empty")
    
    config = getattr(body, "config", {}) or body.get("config", {})
    stream_resumable = getattr(body, "stream_resumable", False)
    stream_subgraphs = getattr(body, "stream_subgraphs", False)

    try:
        # NOTE: get the input from the endpoint.
        
        async for stream_mode, chunk in graph.astream(
            input=input,
            config=config or {"configurable": {"thread_id": thread_id}, "recursion_limit": 5000},
            stream_mode=["messages"],
            # subgraphs=stream_subgraphs,
        ):
                        
            if stream_mode == "values":
                if messages := chunk.get("messages", None):
                    dict_messages = [msg.model_dump(exclude_none=True) if isinstance(msg, BaseMessage) else msg for msg in messages]
                    
                    await redis_client.publish(
                        f"run:{run_id}:stream",
                        json.dumps(
                            {
                                "event": "values",
                                "data": {
                                    "messages": dict_messages
                                },
                                "run_id": run_id,
                                "thread_id": thread_id,
                            }
                        )
                    )
                    
            if stream_mode == "messages":
                if isinstance(chunk, tuple):
                    chunk_list = []
                    for item in chunk:
                        if isinstance(item, BaseMessage):
                            # TODO: create a custom serialization method to handle empty fields.
                            chunk_list.append(item.model_dump(exclude_none=True))
                        else:
                            chunk_list.append(item)
                    
                await redis_client.publish(
                    f"run:{run_id}:stream",
                    json.dumps(
                        {
                            "event": "messages",
                            "data": chunk_list,
                            "run_id": run_id,
                            "thread_id": thread_id
                        }
                    )
                )    
                
                    
        await redis_client.publish(
            f"run:{run_id}:stream",
            json.dumps(
                {
                    "event": "status",
                    "status": "completed",
                    "run_id": run_id,
                    "thread_id": thread_id,
                }
            ),
        )
        
    except Exception as e:
        import traceback    
        traceback.print_exc()
        # On error, send error status
        await redis_client.publish(
            f"run:{run_id}:stream",
            json.dumps(
                {
                    "type": "status",
                    "status": "error",
                    "error": str(e),
                    "run_id": run_id,
                    "thread_id": thread_id,
                }
            ),
        )
        print(f"Error processing run {run_id}: {e}")

async def main():

    while True:
        print("Waiting for work...")
        result = await redis_client.blpop("run:queue", timeout=3)

        if result:
            run_id = result[1]
            print(f"Received run with ID: {run_id}")
            asyncio.create_task(process_run(run_id))


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("Shutting down...")
        sys.exit(0)
    except Exception as e:
        print(f"Error: {e}")
        sys.exit(1)
