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
import uuid
import logging
from langgraph_sdk.schema import Thread
from ...utils import state_snapshot_to_thread_state
from ...schema import (
    ThreadCreate,
    ThreadPatch,
    ThreadSearchRequest,
    ThreadStateSearch,
)
from ..utils import authenticate_user
from ..services.threads import Threads

logger = logging.getLogger("threads")
threads_router = APIRouter(prefix="/threads")


@threads_router.post("")
async def create_thread(
    body: ThreadCreate = Body(...),
    user_id: str = Depends(authenticate_user),
) -> Thread:
    """Create a new thread."""

    if body.get("supersteps", None) or body.get("values", None):
        logger.error(f"Got Supersteps or values, but supersteps or values not supported yet")
        raise ValueError("supersteps or values not supported yet")

    thread_id = body.get("thread_id", None) or str(uuid.uuid4())
    metadata = body.get("metadata", None) or {}

    try:
        created = await Threads.put(
            thread_id,
            user_id=user_id,
            metadata=metadata,
            if_exists="raise",
            ttl=body.get("ttl", None),
        )
    except Exception as e:
        logger.error(f"Error creating thread: {e}")
        raise HTTPException(
            status_code=500, detail=f"Internal server error: {e} while creating thread"
        )

    return created


@threads_router.post("/search")
async def search_threads(
    user_id: str = Depends(authenticate_user), 
    body: ThreadSearchRequest = Body(...)
):
    """Search for threads.
    This endpoint also functions as the endpoint to list all threads.
    """
    # NOTE: implement the proper filtering based on the request body.

    try:
        threads, _next_offset = await Threads.search(
            user_id=user_id,
            ids=body.get("ids", None),
            metadata=body.get("metadata", None),
            values=body.get("values", None),
            status=body.get("status", None),
            limit=body.get("limit", 100),
            offset=body.get("offset", 0),
            sort_by=body.get("sort_by", None),
            sort_order=body.get("sort_order", None),
            select=body.get("select", None),
        )

    except Exception as e:
        logger.error(f"Error searching threads: {e}")
        raise HTTPException(
            status_code=500, detail="Internal server error while searching threads"
        )

    return threads


@threads_router.get("/{thread_id}/state")
async def get_thread_state(
    thread_id: str = Path(..., description="The ID of the thread"),
    user_id: str = Depends(authenticate_user),
    subgraphs: bool = Query(False, description="Whether to include subgraphs in the response."),
):
    """Get state for a thread.
    
    The latest state of the thread (i.e. latest checkpoint) is returned.
    This is a fast alternative to fetching full history.
    """
    try:
        state_snapshot = await Threads.State.get(
            config={"configurable": {"thread_id": thread_id}},
            user_id=user_id,
            subgraphs=subgraphs,
        )
        
        thread_state = state_snapshot_to_thread_state(state_snapshot)
        
        logger.debug(f"Fetched latest state for thread {thread_id}")
        return thread_state
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching thread state for thread {thread_id}: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Internal server error: {e} while fetching thread state"
        )


@threads_router.post("/{thread_id}/history")
async def get_thread_history_post(
    thread_id: str = Path(...),
    body: ThreadStateSearch = Body(...),
    user_id: str = Depends(authenticate_user),
):
    """Get all past states for a thread."""

    try:
        states = await Threads.State.list(
            config={"configurable": {"thread_id": thread_id}},
            user_id=user_id,
            limit=body.get("limit", 10),
            before=body.get("before", None),
            metadata=body.get("metadata", None),
        )
        
        # Convert StateSnapshots to ThreadState format
        thread_states = [
            state_snapshot_to_thread_state(state)
            for state in states
        ]
        
        if not thread_states:
            logger.warning(f"No states found for thread {thread_id}")
        
        return thread_states
    
    except HTTPException:
        raise
    
    except Exception as e:
        logger.error(f"Error fetching thread history for thread {thread_id}: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Internal server error: {e} while fetching thread history"
        )


@threads_router.patch("/{thread_id}")
async def patch_thread(
    thread_id: str = Path(..., description="The ID of the thread"),
    body: ThreadPatch = Body(...),
    user_id: str = Depends(authenticate_user),
) -> Thread:
    """Update a thread"""
    
    try:
        updated_thread = await Threads.patch(
            thread_id,
            user_id=user_id,
            metadata=body.get("metadata", {}),
            ttl=body.get("ttl", None),
        )

        if not updated_thread:
            logger.error(f"Thread {thread_id} not found for user {user_id}")
            raise HTTPException(status_code=404, detail=f"Thread {thread_id} not found")

        return updated_thread
        
    except HTTPException:
        raise
    
    except Exception as e:
        logger.error(f"Error updating thread {thread_id}: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Internal server error: {e} while updating thread"
        )


@threads_router.delete("/{thread_id}")
async def delete_thread(
    thread_id: str = Path(..., description="The ID of the thread"),
    user_id: str = Depends(authenticate_user),
):
    """Delete a thread by ID."""
    try:
        await Threads.delete(thread_id, user_id)
        
    except HTTPException:
        raise
    
    except Exception as e:
        logger.error(f"Error deleting thread {thread_id}: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Internal server error: {e} while deleting thread"
        )


@threads_router.post("/{thread_id}/copy")
async def copy_thread(
    thread_id: str = Path(..., description="The ID of the thread to copy"),
    user_id: str = Depends(authenticate_user),
) -> Thread:
    """Create a copy of an existing thread with all its checkpoint data."""
    try:
        copied_thread = await Threads.copy(thread_id, user_id)
        
        if not copied_thread:
            raise HTTPException(
                status_code=404,
                detail=f"Thread with ID {thread_id} not found"
            )
        
        return copied_thread
        
    except HTTPException:
        raise
    
    except Exception as e:
        logger.error(f"Error copying thread {thread_id}: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Internal server error: {e} while copying thread"
        )


@threads_router.delete("/{thread_id}/checkpoints/{checkpoint_id}")
async def delete_from_checkpoint(
    thread_id: str = Path(..., description="The ID of the thread"),
    checkpoint_id: str = Path(..., description="The checkpoint ID to delete from (inclusive)"),
    user_id: str = Depends(authenticate_user),
):
    """Delete all checkpoints from a specific checkpoint onwards, effectively rolling back the thread.
    
    This will delete the specified checkpoint and all its descendants, rolling the thread back
    to the parent of the specified checkpoint.
    """
    try:
        await Threads.delete_from_checkpoint(thread_id, checkpoint_id, user_id)
        
    except HTTPException:
        raise
    
    except Exception as e:
        logger.error(f"Error deleting checkpoints from {checkpoint_id} in thread {thread_id}: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Internal server error: {e} while deleting checkpoints"
        )


