from fastapi import APIRouter, Header, Query, BackgroundTasks, Request, Body, Depends, HTTPException
from fastapi.responses import StreamingResponse
import time
import uuid
import asyncio
import json
import logging
import sys
from pydantic import BaseModel, Field
from typing import Optional, Dict, Any, List
from langgraph_sdk.schema import Thread
from ..models import ThreadCreate, ThreadSearchRequest
from langgraph.graph import START, END, StateGraph, MessagesState
from langgraph.store.base import Item

from ..utils.utils import state_snapshot_to_thread_state
from core.worker import process_run
from core.clients.redis_client import redis_client
from core.clients.supabase_client import DBConnection
from core.clients.langgraph_store import store
from core.clients.langgraph_checkpointer import checkpointer
from ..utils.auth_utils import authenticate_user

import pprint
pp = pprint.PrettyPrinter(indent=1, width=80)

logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    stream=sys.stdout,
)
logger = logging.getLogger("threads")



threads_router = APIRouter()


class RunCreate(BaseModel):
    """Schema for creating a run."""

    assistant_id: Optional[str] = Field(
        None, description="ID of the assistant to use for this run"
    )
    input: Optional[Dict[str, Any]] = Field(None, description="Input for the run")
    stream_mode: Optional[List[str]] = Field(
        None, description="Stream modes for the run"
    )
    config: Optional[Dict[str, Any]] = Field(
        None, description="Configuration for the run"
    )
    context: Optional[Dict[str, Any]] = Field(None, description="Context for the run")
    metadata: Optional[Dict[str, Any]] = Field(None, description="Metadata for the run")

thread_ids = []

@threads_router.post("", summary="Create a new thread", tags=["threads"])
async def create_thread(
    body: ThreadCreate = Body(...),
    user_id: str = Depends(authenticate_user),
)->Thread:
    """Create a new thread. This is a minimal implementation that just returns a thread ID."""
    # TODO: check if the thread is already exists
    
    if user_id:
        print(f"Authenticated user_id: {user_id}")
        
    if getattr(body, "supersteps", None) or getattr(body, "values", None):
        logger.error(f"Got Supersteps or values, but supersteps or values not supported yet")
        raise ValueError("supersteps or values not supported yet")
    
    thread = Thread(
        thread_id=body.thread_id or str(uuid.uuid4()),
        created_at=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        updated_at=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        metadata=body.metadata or {},
        status="idle",
        values={},
        interrupts={}
    )
    
    db = DBConnection()
    await db.initialize()
    client = await db.client
    
    result = await client.table("threads").insert(
        {
            "user_id": user_id, 
            **thread
        }).execute()
    
    print(f"Insert Result: {result.data}")
    
    return thread



@threads_router.post(
    "/{thread_id}/runs/stream",
    summary="stream output from a run",
    tags=["threads", "runs"],
)
async def stream_thread_run(
    thread_id: str,
    body: Any = Body(...),
):
    """Join a run stream.
    This endpoint streams output in real-time from a run.
    If the run has been created with stream_resumable=true, the stream can be resumed from the last seen event ID.
    """
    run_id = f"run_{uuid.uuid4().hex[:8]}"
    
    asyncio.create_task(process_run(run_id=run_id, thread_id=thread_id, body=body))

    async def generator():
        pubsub = redis_client.pubsub()
        await pubsub.subscribe(f"run:{run_id}:stream")
        print(f"[GENERATOR] Subscribed to Redis channel: run:{run_id}:stream")

        try:
            async for message in pubsub.listen():  # listens indefinitely
                if message is None:
                    continue
                if message["type"] == "message":
                    data = message["data"]

                    if isinstance(data, bytes):
                        data = data.decode("utf-8")
                    else:
                        logger.debug(f"Unexpected data type: {type(data)}")

                    if isinstance(data, str):
                        data = json.loads(data)
                    else:
                        logger.debug(f"Unexpected data type after decode: {type(data)}")

                    if data.get("event", None) == "status":
                        if status:=data.get("status", None) in ["completed", "error"]:
                            print(f"[GENERATOR] Received terminal status: {status}, ending stream.")
                            break
                                        
                    yield f"event: {data.get('event')}\ndata: {json.dumps(data.get('data'))}\n\n"

        except asyncio.CancelledError:
            print(f"[GENERATOR] Client disconnected, cancelling subscription")

        finally:
            await pubsub.unsubscribe(f"run:{run_id}:stream")
            await pubsub.close()
            print(f"[GENERATOR] Unsubscribed and closed Redis pubsub")
    
    async def dummy():
        yield f"event: messages\ndata: {json.dumps(
            [
                {"id": "hello", "type": "ai", "content": "This is a dummy message"},
                {'thread_id': '123', 'langgraph_step': 2, 'langgraph_node': 'model_node2', 'langgraph_triggers': ('branch:to:model_node2',), 'langgraph_path': ('__pregel_pull', 'model_node2'), 'langgraph_checkpoint_ns': 'model_node2:eca20bfc-91dc-e838-5550-5239da560db7'}
            ]
        )}\n\n"
        
    response = StreamingResponse(
        generator(),
        # dummy(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-transform",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
            "Content-Type": "text/event-stream",
            "Access-Control-Allow-Origin": "*",
        },
    )
    
    return response


@threads_router.post("/search", summary="Search for threads", tags=["threads"])
async def search_threads(
    body: ThreadSearchRequest = Body(...),
    user_id: str = Depends(authenticate_user)
):
    """
    Search for threads. This is a minimal implementation that just returns an empty list
    since we're focusing on direct runs rather than thread-based operations.
    """
    try:
        db = DBConnection()
        await db.initialize()
        client = await db.client
        query = client.table("threads").select("*").eq("user_id", user_id)
            
        if body.ids:
            query = query.in_("thread_id", body.ids)
        
        # if body.metadata:
        #     for key, value in body.metadata.items():
        #         query = query.eq(f"metadata->{key}", value)
        
        if body.limit:
            query = query.limit(body.limit)
        
        if body.offset:
            query = query.offset(body.offset)
        
        result = await query.execute()
        
        threads = result.data or []   
    
    except Exception as e:
        logger.error(f"Error searching threads: {e}")
        raise HTTPException(
            status_code=500,
            detail="Internal server error while searching threads"
        )
              
    return threads


@threads_router.post(
    "/{thread_id}/history",
    summary="Get thread history",
    tags=["threads"],
)
async def get_thread_history(
    thread_id: str,
    body: Any = Body(...),
):
    """
    Get the history of a thread. This endpoint is critical for the UI's initialization.
    The UI calls this repeatedly during startup which can cause state resets.
    Uses the thread cache to ensure consistent messages.
    """
    pp.pprint(f"BODY: {body}")
    thread_states = []
    
    try:
        graph = StateGraph(MessagesState).add_edge(START, END).compile(checkpointer=checkpointer)
        async for state_snapshot in graph.aget_state_history(
            config={"configurable": {"thread_id": thread_id}},
            # limit=body.get("limit", None)
        ):

            thread_state = state_snapshot_to_thread_state(state_snapshot)
            # pp.pprint(thread_state)
            thread_states.append(thread_state)
             
        return thread_states
       
    except Exception as e:
        print(f"Error fetching thread history for thread {thread_id}: {e}")
        return []
