from fastapi import APIRouter, Header, Query, BackgroundTasks, Request, Body, Depends, HTTPException, Path
from fastapi.responses import StreamingResponse
import time
import uuid
import asyncio
import json
import logging
from langgraph_sdk.schema import Thread
from langgraph_api.state import state_snapshot_to_thread_state
from ...schema import ThreadCreate, ThreadSearchRequest, RunCreateStateful, ThreadStateSearch, Run
from langgraph.graph import START, END, StateGraph, MessagesState
# from ...worker import graph
import pprint

# from ..utils.utils import state_snapshot_to_thread_state
from agent_platform.worker import process_run
from core.clients import get_redis, get_supabase, checkpointer
from ..utils import authenticate_user

pp = pprint.PrettyPrinter(indent=1, width=80)
logger = logging.getLogger("threads")

threads = APIRouter()


@threads.post(
    "", 
    summary="Create a new thread", 
    tags=["threads"]
)
async def create_thread(
    body: ThreadCreate = Body(...),
    user_id: str = Depends(authenticate_user),
) -> Thread:
    """Create a new thread."""
    
    if user_id:
        logger.debug(f"Authenticated user_id: {user_id}")

    if body.get("supersteps") or body.get("values"):
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
    
    try:
        supabase_client = await get_supabase()
        result = await supabase_client.table("threads").insert({"user_id": user_id, **thread}).execute()
        
        if error := getattr(result, "error", None) :
            logger.error(f"Error inserting thread into database: {error}")
            raise HTTPException(status_code=500, detail=f"Internal server error: {error} while creating thread")

        logger.debug(f"Thread created: {getattr(result, 'data', None)}")
        
    except Exception as e:
        logger.error(f"Error creating thread: {e}")
        raise HTTPException(status_code=500, detail=f"Internal server error: {e} while creating thread")
        
    return thread


@threads.post(
    "/{thread_id}/runs/stream",
    summary="stream output from a run",
    tags=["threads", "runs"],
)
async def stream_thread_run(
    # user_id: str = Depends(authenticate_user),
    thread_id: str = Path(...),
    body: RunCreateStateful = Body(...),
):
    """Create a run in existing thread. Stream the output."""
    
    pp.pprint(body)
    
    on_disconnect = body.pop("on_disconnect", None)
    if_not_exists = body.pop("if_not_exists", None)
    
    run_id = str(uuid.uuid4())
    
    # FIXME: check thread if_not_exits, 
    asyncio.create_task(
        process_run(
            Run(
                run_id=run_id,
                thread_id=thread_id,
                assistant_id=body.pop("assistant_id", None),
                status="pending",
                metadata=body.pop("metadata", {}),
                multitask_strategy=body.pop("multitask_strategy", "enqueue"),
                created_at=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                updated_at=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                kwargs={**body}, # Always include kwargs after popping Run fields.
            )
        )
    )

    async def generator():
        redis_client = get_redis()
        pubsub = redis_client.pubsub()
        await pubsub.subscribe(f"run:{run_id}:stream")

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
            logger.debug("Client disconnected, cancelling generator.")
            
        finally:
            await pubsub.unsubscribe(f"run:{run_id}:stream")
            await pubsub.close()
            logger.debug("Generator cleanup complete.")
    
    response = StreamingResponse(
        generator(),
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


@threads.post(
    "/search", 
    summary="Search for threads", 
    tags=["threads"]
)
async def search_threads(
    user_id: str = Depends(authenticate_user),
    body: ThreadSearchRequest = Body(...)
):
    """Search for threads.
    This endpoint also functions as the endpoint to list all threads.
    """
    # NOTE: implement the proper filtering based on the request body.
    try:
        supabase_client = await get_supabase()
        query = (
            supabase_client
            .table("threads")
            .select("*")
            .eq("user_id", user_id)
        )

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


@threads.post(
    "/{thread_id}/history",
    summary="Get thread history",
    tags=["threads"],
)
async def get_thread_history_post(
    thread_id: str = Path(...),
    body: ThreadStateSearch = Body(...),
):
    """Get all past states for a thread.  NOTE: In the official docs, state snapshots are fetchted from the graph_id configured in the thread_id. 
    For now we will use the new minimal compiled graph. """
    
    try:
        graph = StateGraph(MessagesState).add_edge(START, END).compile(checkpointer=checkpointer)
        states = [
            state_snapshot_to_thread_state(state)
            async for state in graph.aget_state_history(
                config={"configurable": {"thread_id": thread_id}},
                # filter=
                before=body.get("before", None),
                limit=body.get("limit", None)
            )
        ]
        if not states:
            logger.warning(f"No states found for thread {thread_id}")
        
        return states
        
    except Exception as e:
        logger.error(f"Error fetching thread history for thread {thread_id}: {e}")
        return []
