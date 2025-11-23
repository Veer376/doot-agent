"""API routes for managing runs, including streaming run outputs.
For the runs particular we are looking to use the business logic."""

from fastapi import APIRouter, Header, Query, BackgroundTasks, Request, Body, Path
from fastapi.responses import StreamingResponse
import time
import uuid
import asyncio
import json
from typing import Optional, Dict, Any, List
from orbit_core.clients.redis_client import get_redis
from ...schema import RunCreateStateful, Run
from ...worker import process_run
from pydantic import BaseModel, Field
import logging

logger = logging.getLogger(__name__)
runs_router = APIRouter()

@runs_router.post(
    "/threads/{thread_id}/runs/stream", 
    summary="stream output from a run", 
    tags=["threads", "runs"],
)
async def stream_run(
    # user_id: str = Depends(authenticate_user),
    thread_id: str = Path(...),
    body: RunCreateStateful = Body(...),
):
    """Create a run in existing thread. Stream the output."""

    # pp.pprint(body)

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
                kwargs={**body},  # Always include kwargs after popping Run fields.
            )
        )
    )

    async def generator():
        redis_client = await get_redis()
        pubsub = redis_client.pubsub()
        await pubsub.subscribe(f"run:{run_id}:stream")

        try:
            async for message in pubsub.listen():  # listens indefinitely
                
                if message is None:
                    continue

                if message["type"] == "message":
                    data = message["data"]
                    
                    if isinstance(data, str):
                        data = json.loads(data)
                    else:
                        logger.debug(f"Unexpected data type for pubsub data: {type(data)}")

                    if data.get("event", None) == "status":
                        if status := data.get("status", None) in ["completed", "error"]:
                            print(
                                f"[GENERATOR] Received terminal status: {status}, ending stream."
                            )
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
