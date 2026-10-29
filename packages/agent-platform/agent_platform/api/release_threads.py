"""Supported thread endpoints backed by the existing Threads table service."""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from typing import Any
from uuid import uuid4
from .utils import authenticate_user
from .services.threads import Threads
from ..graph import get_graph
from ..utils import state_snapshot_to_thread_state

router = APIRouter(prefix="/threads")
class ThreadInput(BaseModel):
    thread_id: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    if_exists: str = "raise"

async def owned(thread_id, user_id):
    thread = await Threads.get(thread_id, user_id=user_id)
    if not thread:
        raise HTTPException(404, "Thread not found")
    return thread

@router.post("")
async def create(body: ThreadInput, user_id=Depends(authenticate_user)):
    return await Threads.put(body.thread_id or str(uuid4()), user_id=user_id,
        metadata=body.metadata, if_exists=body.if_exists)

@router.post("/search")
async def search(body: dict, user_id=Depends(authenticate_user)):
    result, _ = await Threads.search(user_id=user_id, ids=body.get("ids"),
        metadata=body.get("metadata"), values=None, status=body.get("status"),
        limit=min(body.get("limit", 100), 100), offset=body.get("offset", 0),
        sort_by=body.get("sort_by"), sort_order=body.get("sort_order"))
    return result

@router.get("/{thread_id}")
async def get(thread_id: str, user_id=Depends(authenticate_user)):
    return await owned(thread_id, user_id)

@router.patch("/{thread_id}")
async def patch(thread_id: str, body: dict, user_id=Depends(authenticate_user)):
    thread = await owned(thread_id, user_id)
    from orbit_core.clients import get_supabase
    db = await get_supabase()
    metadata = {**thread.get("metadata", {}), **body.get("metadata", {})}
    result = await db.table("threads").update({"metadata": metadata}).eq("thread_id", thread_id).eq("user_id",user_id).execute()
    return result.data[0]

@router.get("/{thread_id}/state")
async def state(thread_id: str, user_id=Depends(authenticate_user)):
    thread = await owned(thread_id, user_id)
    graph = await get_graph(thread.get("metadata", {}).get("assistant_id", "chat_agent"))
    result = await graph.aget_state({"configurable": {"thread_id": thread_id}})
    return state_snapshot_to_thread_state(result)

@router.post("/{thread_id}/history")
async def history(thread_id: str, body: dict, user_id=Depends(authenticate_user)):
    thread = await owned(thread_id, user_id)
    graph = await get_graph(thread.get("metadata", {}).get("assistant_id", "chat_agent"))
    return [state_snapshot_to_thread_state(s) async for s in graph.aget_state_history(
        {"configurable": {"thread_id": thread_id}}, limit=min(body.get("limit", 10),100))]
