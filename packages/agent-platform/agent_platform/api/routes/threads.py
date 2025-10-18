"""API routes for managing threads. prefix has been removed because
1. route endpoint created problem.
2. endpoint associated to the runs has threads in it."""

from fastapi import (
    APIRouter,
    Header,
    Query,
    Body,
    Depends,
    HTTPException,
    Path,
)
import time
import uuid
import logging
from langgraph_sdk.schema import Thread
from ...state import state_snapshot_to_thread_state
from ...schema import (
    ThreadCreate,
    ThreadPatch,
    ThreadSearchRequest,
    ThreadStateSearch,
)
from langgraph.graph import START, END, StateGraph, MessagesState
import pprint
from orbit_core.clients import get_supabase
from orbit_core.clients.checkpointer import get_checkpointer
from ..utils import authenticate_user

logger = logging.getLogger("threads")
threads_router = APIRouter(prefix="/threads")


@threads_router.post(
    "",
    summary="Create a new thread",
    tags=["threads"])
async def create_thread(
    body: ThreadCreate = Body(...),
    user_id: str = Depends(authenticate_user),
) -> Thread:
    """Create a new thread."""
    # TODO: handle the TTL

    if user_id:
        logger.debug(f"Authenticated user_id: {user_id}")

    if body.get("supersteps", None) or body.get("values", None):
        logger.error(
            f"Got Supersteps or values, but supersteps or values not supported yet"
        )
        raise ValueError("supersteps or values not supported yet")

    thread = Thread(
        thread_id=body.get("thread_id", None) or str(uuid.uuid4()),
        created_at=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        updated_at=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        metadata=body.get("metadata", None) or {},
        status="idle",
        values={},
        interrupts={},
    )

    try:
        supabase_client = await get_supabase()
        result = (
            await supabase_client.table("threads")
            .insert({"user_id": user_id, **thread})
            .execute()
        )

        if error := getattr(result, "error", None):
            logger.error(f"Error inserting thread into database: {error}")
            raise HTTPException(
                status_code=500,
                detail=f"Internal server error: {error} while creating thread",
            )

        logger.debug(f"Thread created: {getattr(result, 'data', None)}")

    except Exception as e:
        logger.error(f"Error creating thread: {e}")
        raise HTTPException(
            status_code=500, detail=f"Internal server error: {e} while creating thread"
        )

    return thread


@threads_router.post(
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

        # Determine which fields to select
        # Note: select() must be called first in Supabase query builder
        select_fields = "*"
        if select := body.get("select", None):
            # Map ThreadSelectField to actual database columns
            # The database has: thread_id, user_id, created_at, updated_at, metadata, status
            # Some fields like 'config', 'context', 'values', 'interrupts' may be in metadata or separate columns
            select_fields = ",".join(select)  # Trust that these are valid column names

        # Build query starting with select
        query = (
            supabase_client.table("threads")
            .select(select_fields)
            .eq("user_id", user_id)
        )

        if ids := body.get("ids", None):
            query = query.in_("thread_id", ids)

        if status := body.get("status", None):
            query = query.eq("status", status)

        # TODO: Implement metadata filtering properly with JSONB queries
        # if body.metadata:
        #     for key, value in body.metadata.items():
        #         query = query.eq(f"metadata->{key}", value)

        # TODO: Implement values filtering with JSONB queries
        # if body.values:
        #     for key, value in body.values.items():
        #         query = query.eq(f"values->{key}", value)

        if limit := body.get("limit", None):
            query = query.limit(limit)

        if offset := body.get("offset", None):
            query = query.offset(offset)

        if sort_by := body.get("sort_by", "updated_at"):
            sort_order = body.get("sort_order", "desc")
            query = query.order(sort_by, desc=(sort_order == "desc"))

        result = await query.execute()

        threads = result.data or []

    except Exception as e:
        logger.error(f"Error searching threads: {e}")
        raise HTTPException(
            status_code=500, detail="Internal server error while searching threads"
        )

    return threads


@threads_router.post(
    "/{thread_id}/history",
    summary="Get thread history", 
    tags=["threads"]
)
async def get_thread_history_post(
    thread_id: str = Path(...),
    body: ThreadStateSearch = Body(...),
):
    """Get all past states for a thread.  NOTE: In the official docs, state snapshots are fetchted from the graph_id configured in the thread_id.
    For now we will use the new minimal compiled graph. Later we will get it from the thread itself, as we also have to maintain the agent_id in the thread
    to preserve the previously used agent, if there would be multiple agents for per graph we will use agent namespace signature <graph_id>:<agent_id> to fetch the correct graph.
    Though in cases of the non compiled where we have to pass the assistant details to get the compiled graph, so it this is little bit complex, we will think about it later.
    Minimal graph seems the easiest solution for future also. 'll see."""

    try:
        graph = StateGraph(MessagesState).add_edge(START, END).compile(checkpointer=get_checkpointer())
        states = [
            state_snapshot_to_thread_state(
                state
            )
            async for state in graph.aget_state_history(
                config={"configurable": {"thread_id": thread_id}},
                # TODO: Implement filtering
                before=body.get("before", None),
                limit=body.get("limit", None),
            )
        ]
        if not states:
            logger.warning(f"No states found for thread {thread_id}")
        return states
    
    except Exception as e:
        logger.error(f"Error fetching thread history for thread {thread_id}: {e}")
        return []


@threads_router.patch(
    "/{thread_id}",
    summary="Update a thread",
    tags=["threads"]
)
async def patch_thread(
    thread_id: str = Path(..., description="The ID of the thread"),
    body: ThreadPatch = Body(...),
    user_id: str = Depends(authenticate_user),
) -> Thread:
    """Update a thread"""
    
    if user_id:
        logger.debug(f"Authenticated user_id: {user_id}")

    try:
        supabase_client = await get_supabase()
        
        # First, verify the thread exists and belongs to the user
        existing_thread_result = (
            await supabase_client.table("threads")
            .select("*")
            .eq("thread_id", thread_id)
            .eq("user_id", user_id)
            .execute()
        )
        
        if not existing_thread_result.data:
            logger.error(f"Thread {thread_id} not found for user {user_id}")
            raise HTTPException(
                status_code=404,
                detail=f"Thread {thread_id} not found"
            )
        
        existing_thread = existing_thread_result.data[0]
        
        # Note: updated_at is automatically set by database trigger
        update_payload = {}
        
        # Merge metadata if provided
        if metadata := body.get("metadata", None):
            existing_metadata = existing_thread.get("metadata", {}) or {}
            merged_metadata = {**existing_metadata, **metadata}
            update_payload["metadata"] = merged_metadata
        
        # Update TTL if provided
        if ttl := body.get("ttl", None):
            update_payload["ttl"] = ttl
        
        # Perform the update
        result = (
            await supabase_client.table("threads")
            .update(update_payload)
            .eq("thread_id", thread_id)
            .eq("user_id", user_id)
            .execute()
        )
        
        if error := getattr(result, "error", None):
            logger.error(f"Error updating thread {thread_id}: {error}")
            raise HTTPException(
                status_code=500,
                detail=f"Internal server error: {error} while updating thread"
            )
        
        updated_data = result.data[0] if result.data else existing_thread
        
        # Convert to Thread schema
        thread = Thread(
            thread_id=updated_data["thread_id"],
            created_at=updated_data["created_at"],
            updated_at=updated_data["updated_at"],
            metadata=updated_data.get("metadata", {}),
            status=updated_data.get("status", "idle"),
            values=updated_data.get("values", {}),
            interrupts=updated_data.get("interrupts", {}),
        )
        
        logger.debug(f"Thread {thread_id} updated successfully")
        return thread
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating thread {thread_id}: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Internal server error: {e} while updating thread"
        )


@threads_router.delete(
    "/{thread_id}",
    summary="Delete a thread by ID.",
    tags=["threads"],
    status_code=200
)
async def delete_thread(
    thread_id: str = Path(..., description="The ID of the thread"),
    user_id: str = Depends(authenticate_user),
):
    """Delete a thread by ID."""
    
    if user_id:
        logger.debug(f"Authenticated user_id: {user_id}")

    try:
        supabase_client = await get_supabase()
        
        # Verify thread exists and belongs to user, then delete
        result = (
            await supabase_client.table("threads")
            .delete()
            .eq("thread_id", thread_id)
            .eq("user_id", user_id)
            .execute()
        )
        
        # If no rows were deleted, thread doesn't exist or doesn't belong to user
        if not result.data:
            logger.error(f"Thread {thread_id} not found for user {user_id}")
            raise HTTPException(
                status_code=404,
                detail=f"Thread {thread_id} not found"
            )
        
        if error := getattr(result, "error", None):
            logger.error(f"Error deleting thread {thread_id}: {error}")
            raise HTTPException(
                status_code=500,
                detail=f"Internal server error: {error} while deleting thread"
            )
        
        logger.info(f"Thread {thread_id} deleted successfully by user {user_id}")
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting thread {thread_id}: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Internal server error: {e} while deleting thread"
        )

