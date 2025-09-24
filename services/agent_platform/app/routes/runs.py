from fastapi import APIRouter, Header, Query, BackgroundTasks, Request, Body, Path
from fastapi.responses import StreamingResponse
import time
import uuid
import asyncio
import json
from typing import Optional, Dict, Any, List
from core.clients.redis_client import redis_client
from core.worker import process_run
from pydantic import BaseModel, Field
import logging

logger = logging.getLogger(__name__)

runs_router = APIRouter()


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




@runs_router.post(
    "/stream",
    summary="stream output from a run",
    tags=["runs"],
)
async def stream_thread_run(
    request: Request,
):
    """Join a run stream.
    This endpoint streams output in real-time from a run.
    If the run has been created with stream_resumable=true, the stream can be resumed from the last seen event ID.

    This endpoint supports both UI clients and RemoteGraph clients.
    """
    run_id = f"run_{uuid.uuid4().hex[:8]}"

    # Check the request body and headers to determine if this is a RemoteGraph client
    # or a UI client (like useStream() in React)
    body = await request.json()
    logger.debug(f"Request body: {body}")
    logger.debug(f"Request headers: {request.headers}")

    async def generator():
        # 1. Send initial status
        status_message = {"type": "status", "status": "running", "run_id": run_id}
        print(f"[UI] Sending status: {json.dumps(status_message)}")
        yield f"data: {json.dumps(status_message)}\n\n"
        await asyncio.sleep(0.5)
        # 2. Send a UI message with proper format for frontend display
        msg_id = f"msg_{uuid.uuid4()}"
        ui_message = {
            "type": "update",  # This is what the UI expects
            "messages": [
                {
                    "id": msg_id,
                    "type": "ai",
                    "role": "assistant",
                    "content": [
                        {
                            "type": "text",
                            "text": "Hello from Orbit Agent UI! This is the format useStream() expects.",
                        }
                    ],
                    "created_at": int(time.time()),
                }
            ],
        }
        print(f"[UI] Sending message: {json.dumps(ui_message)}")
        yield f"data: {json.dumps(ui_message)}\n\n"
        await asyncio.sleep(0.5)
        # 3. Send completion status
        completion_status = {
            "type": "status",
            "status": "completed",
            "run_id": run_id,
        }
        print(f"[UI] Sending completion: {json.dumps(completion_status)}")
        yield f"data: {json.dumps(completion_status)}\n\n"  # Return StreamingResponse with proper SSE headers to match Suna API

    print(f"[RESPONSE] Creating StreamingResponse with generator")
    
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
    print(f"[RESPONSE] Response headers: {response.headers}")
    print(f"[RESPONSE] StreamingResponse created and returned")
    return response
