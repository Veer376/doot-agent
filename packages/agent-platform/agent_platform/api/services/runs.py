"""Runs service - Business logic for run operations."""

from __future__ import annotations

import asyncio
import copy
from collections.abc import AsyncIterator, Sequence
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from typing import Literal
from uuid import UUID, uuid4

import structlog
from starlette.exceptions import HTTPException

from langgraph_runtime_inmem.checkpoint import Checkpointer
from langgraph_runtime_inmem.database import InMemConnectionProto, connect
from langgraph_runtime_inmem.inmem_stream import (
    THREADLESS_KEY,
    ContextQueue,
    Message,
    get_stream_manager,
)
from orbit_core.clients import get_supabase

from ...utils import (
    ensure_uuid as _ensure_uuid,
    listen_for_cancellation,
    empty_generator as _empty_generator,
    delete_checkpoints_for_thread as _delete_checkpoints_for_thread,
)

import typing

if typing.TYPE_CHECKING:
    from langgraph_api.asyncio import ValueEvent
    from langgraph_api.schema import (
        IfNotExists,
        MetadataInput,
        MultitaskStrategy,
        QueueStats,
        Run,
        RunSelectField,
        RunStatus,
        StreamMode,
    )

logger = structlog.stdlib.get_logger(__name__)

# Lock for run operations
RUN_LOCK = asyncio.Lock()


class WrappedHTTPException(Exception):
    """Wrapper for HTTPException to allow proper exception handling."""

    def __init__(self, http_exception: HTTPException):
        self.http_exception = http_exception


class Runs:
    @staticmethod
    async def stats(*, user_id: str) -> QueueStats:
        """Get stats about the queue."""
        # Get Supabase client
        supabase_client = await get_supabase()

        # Get pending and running runs
        pending_result = await (
            supabase_client.table("runs")
            .select("*")
            .eq("user_id", user_id)
            .eq("status", "pending")
            .execute()
        )
        pending_runs = pending_result.data or []

        running_result = await (
            supabase_client.table("runs")
            .select("*")
            .eq("user_id", user_id)
            .eq("status", "running")
            .execute()
        )
        running_runs = running_result.data or []

        if not pending_runs and not running_runs:
            return {
                "n_pending": 0,
                "max_age_secs": None,
                "med_age_secs": None,
                "n_running": 0,
            }

        # Get all creation timestamps
        created_times = [run.get("created_at") for run in (pending_runs + running_runs)]
        created_times = [
            t for t in created_times if t is not None
        ]  # Filter out None values

        if not created_times:
            return {
                "n_pending": len(pending_runs),
                "n_running": len(running_runs),
                "max_age_secs": None,
                "med_age_secs": None,
            }

        # Find oldest (max age)
        oldest_time = min(created_times)  # Earliest timestamp = oldest run

        # Find median age
        sorted_times = sorted(created_times)
        median_idx = len(sorted_times) // 2
        median_time = sorted_times[median_idx]

        return {
            "n_pending": len(pending_runs),
            "n_running": len(running_runs),
            "max_age_secs": oldest_time,
            "med_age_secs": median_time,
        }

    @staticmethod
    async def next(wait: bool, limit: int = 1) -> AsyncIterator[tuple[Run, int]]:
        """Get the next run from the queue, and the attempt number.
        1 is the first attempt, 2 is the first retry, etc."""
        now = datetime.now(UTC)

        if wait:
            await asyncio.sleep(0.5)
        else:
            await asyncio.sleep(0)

        async with connect() as conn, RUN_LOCK:
            # Get Supabase client
            supabase_client = await get_supabase()

            # Get pending runs from Supabase, sorted by created_at
            result = await (
                supabase_client.table("runs")
                .select("*")
                .eq("status", "pending")
                .lte("created_at", now.isoformat())
                .order("created_at")
                .limit(limit * 2)  # Get more than needed to handle filtering
                .execute()
            )

            pending_runs = result.data or []

            if not pending_runs:
                return

            # Try to lock and get the first available run
            for _, run in zip(range(limit), pending_runs, strict=False):
                if run["status"] != "pending":
                    continue

                run_id = run["run_id"]
                thread_id = run["thread_id"]

                # Check if thread exists in Supabase
                thread_result = await (
                    supabase_client.table("threads")
                    .select("*")
                    .eq("thread_id", str(thread_id))
                    .execute()
                )

                if not thread_result.data:
                    await logger.awarning(
                        "Unexpected missing thread in Runs.next",
                        thread_id=run["thread_id"],
                    )
                    continue

                if run["status"] != "pending":
                    continue

                # Check if there are any running runs for this thread
                running_result = await (
                    supabase_client.table("runs")
                    .select("*")
                    .eq("thread_id", str(thread_id))
                    .eq("status", "running")
                    .execute()
                )

                if running_result.data:
                    continue

                # Increment attempt counter
                attempt = await conn.retry_counter.increment(run_id)

                # Update run status to "running" in Supabase
                await (
                    supabase_client.table("runs")
                    .update({"status": "running"})
                    .eq("run_id", str(run_id))
                    .execute()
                )
                run["status"] = "running"
                yield run, attempt

    @asynccontextmanager
    @staticmethod
    async def enter(
        run_id: UUID,
        thread_id: UUID | None,
        loop: asyncio.AbstractEventLoop,
        resumable: bool,
    ) -> AsyncIterator[ValueEvent]:
        """Enter a run, listen for cancellation while running, signal when done."
        This method should be called as a context manager by a worker executing a run.
        """
        from langgraph_api.asyncio import SimpleTaskGroup, ValueEvent
        from langgraph_api.utils.stream_codec import STREAM_CODEC

        stream_manager = get_stream_manager()
        # Get control queue for this run (normal queue is created during run creation)
        control_queue = await stream_manager.add_control_queue(run_id, thread_id)

        async with SimpleTaskGroup(cancel=True, taskgroup_name="Runs.enter") as tg:
            done = ValueEvent()
            tg.create_task(
                listen_for_cancellation(control_queue, run_id, thread_id, done)
            )

            # Give done event to caller
            yield done
            # Store the control message for late subscribers
            control_message = Message(
                topic=f"run:{run_id}:control".encode(), data=b"done"
            )
            await stream_manager.put(run_id, thread_id, control_message)

            # Signal done to all subscribers using stream codec
            stream_message = Message(
                topic=f"run:{run_id}:stream".encode(),
                data=STREAM_CODEC.encode("control", b"done"),
            )
            await stream_manager.put(
                run_id, thread_id, stream_message, resumable=resumable
            )

            # Remove the control_queue (normal queue is cleaned up during run deletion)
            await stream_manager.remove_control_queue(run_id, thread_id, control_queue)

    @staticmethod
    async def sweep() -> None:
        """Sweep runs that are no longer running"""
        pass

    @staticmethod
    def _merge_jsonb(*objects: dict) -> dict:
        """Mimics PostgreSQL's JSONB merge behavior"""
        result = {}
        for obj in objects:
            if obj is not None:
                result.update(copy.deepcopy(obj))
        return result

    @staticmethod
    def _get_configurable(config: dict) -> dict:
        """Extract configurable from config, mimicking PostgreSQL's coalesce"""
        return config.get("configurable", {})

    @staticmethod
    async def put(
        assistant_id: UUID,
        kwargs: dict,
        *,
        thread_id: UUID | None = None,
        user_id: str,
        run_id: UUID | None = None,
        status: RunStatus | None = "pending",
        metadata: MetadataInput,
        prevent_insert_if_inflight: bool,
        multitask_strategy: MultitaskStrategy = "reject",
        if_not_exists: IfNotExists = "reject",
        after_seconds: int = 0,
    ) -> AsyncIterator[Run]:
        """Create a run."""
        from langgraph_api.config import FF_RICH_THREADS
        from langgraph_api.schema import Run, Thread

        # Get Supabase client
        supabase_client = await get_supabase()

        # Get assistant
        assistant_result = await (
            supabase_client.table("assistants")
            .select("*")
            .eq("assistant_id", str(assistant_id))
            .eq("user_id", user_id)
            .execute()
        )

        if not assistant_result.data:
            return _empty_generator()

        assistant = assistant_result.data[0]

        if run_id is None:
            run_id = uuid4()
        metadata = metadata if metadata is not None else {}
        config = kwargs.get("config", {})
        temporary = kwargs.get("temporary", False)

        # Handle thread creation/update
        existing_thread = None
        if thread_id:
            thread_result = await (
                supabase_client.table("threads")
                .select("*")
                .eq("thread_id", str(thread_id))
                .eq("user_id", user_id)
                .execute()
            )
            if thread_result.data:
                existing_thread = thread_result.data[0]

        if not existing_thread and (thread_id is None or if_not_exists == "create"):
            # Create new thread
            if thread_id is None:
                thread_id = uuid4()
            if FF_RICH_THREADS:
                thread = Thread(
                    thread_id=thread_id,
                    status="busy",
                    metadata={
                        "graph_id": assistant["graph_id"],
                        "assistant_id": str(assistant_id),
                        **(config.get("metadata") or {}),
                        **metadata,
                    },
                    config=Runs._merge_jsonb(
                        assistant["config"],
                        config,
                        {
                            "configurable": Runs._merge_jsonb(
                                Runs._get_configurable(assistant["config"]),
                            )
                        },
                    ),
                    created_at=datetime.now(UTC),
                    updated_at=datetime.now(UTC),
                    values=b"",
                    user_id=user_id,
                )
            else:
                thread = Thread(
                    thread_id=thread_id,
                    status="idle",
                    metadata={
                        "graph_id": assistant["graph_id"],
                        "assistant_id": str(assistant_id),
                        **(config.get("metadata") or {}),
                        **metadata,
                    },
                    config={},
                    created_at=datetime.now(UTC),
                    updated_at=datetime.now(UTC),
                    values=b"",
                    user_id=user_id,
                )
            await logger.ainfo("Creating thread", thread_id=thread_id)
            await supabase_client.table("threads").insert(thread).execute()
        elif existing_thread:
            # Update existing thread
            if FF_RICH_THREADS and existing_thread["status"] != "busy":
                updates = {
                    "status": "busy",
                    "metadata": Runs._merge_jsonb(
                        existing_thread["metadata"],
                        {
                            "graph_id": assistant["graph_id"],
                            "assistant_id": str(assistant_id),
                        },
                    ),
                    "config": Runs._merge_jsonb(
                        assistant["config"],
                        existing_thread["config"],
                        config,
                        {
                            "configurable": Runs._merge_jsonb(
                                Runs._get_configurable(assistant["config"]),
                                Runs._get_configurable(existing_thread["config"]),
                            )
                        },
                    ),
                    "updated_at": datetime.now(UTC).isoformat(),
                }
                await (
                    supabase_client.table("threads")
                    .update(updates)
                    .eq("thread_id", str(thread_id))
                    .eq("user_id", user_id)
                    .execute()
                )
                existing_thread.update(updates)
        else:
            return _empty_generator()

        # Check for inflight runs if needed
        inflight_result = await (
            supabase_client.table("runs")
            .select("*")
            .eq("thread_id", str(thread_id))
            .eq("user_id", user_id)
            .in_("status", ["pending", "running"])
            .execute()
        )
        inflight_runs = inflight_result.data or []

        if prevent_insert_if_inflight:
            if inflight_runs:

                async def _return_inflight():
                    for run in inflight_runs:
                        yield run

                return _return_inflight()

        # Create new run
        configurable = Runs._merge_jsonb(
            Runs._get_configurable(assistant["config"]),
            (
                Runs._get_configurable(existing_thread["config"])
                if existing_thread
                else {}
            ),
            Runs._get_configurable(config),
            {
                "run_id": str(run_id),
                "thread_id": str(thread_id),
                "graph_id": assistant["graph_id"],
                "assistant_id": str(assistant_id),
                "user_id": (
                    config.get("configurable", {}).get("user_id")
                    or (
                        existing_thread["config"].get("configurable", {}).get("user_id")
                        if existing_thread
                        else None
                    )
                    or assistant["config"].get("configurable", {}).get("user_id")
                    or user_id
                ),
            },
        )
        merged_metadata = Runs._merge_jsonb(
            assistant["metadata"],
            existing_thread["metadata"] if existing_thread else {},
            config.get("metadata") or {},
            metadata,
        )
        new_run = Run(
            run_id=run_id,
            thread_id=thread_id,
            assistant_id=assistant_id,
            metadata=merged_metadata,
            status=status,
            kwargs=Runs._merge_jsonb(
                kwargs,
                {
                    "config": Runs._merge_jsonb(
                        assistant["config"],
                        config,
                        {"configurable": configurable},
                        {
                            "metadata": merged_metadata,
                        },
                    ),
                    "context": Runs._merge_jsonb(
                        assistant.get("context", {}), kwargs.get("context", {})
                    ),
                },
            ),
            multitask_strategy=multitask_strategy,
            created_at=datetime.now(UTC) + timedelta(seconds=after_seconds),
            updated_at=datetime.now(UTC),
            user_id=user_id,
        )
        await supabase_client.table("runs").insert(new_run).execute()

        async def _yield_new():
            yield new_run
            for r in inflight_runs:
                yield r

        return _yield_new()

    @staticmethod
    async def get(
        run_id: UUID,
        *,
        thread_id: UUID,
        user_id: str,
    ) -> AsyncIterator[Run]:
        """Get a run by ID."""
        # Get Supabase client
        supabase_client = await get_supabase()

        # Get run from Supabase
        result = await (
            supabase_client.table("runs")
            .select("*")
            .eq("run_id", str(run_id))
            .eq("thread_id", str(thread_id))
            .eq("user_id", user_id)
            .execute()
        )

        async def _yield_result():
            if result.data:
                yield result.data[0]

        return _yield_result()

    @staticmethod
    async def delete(
        run_id: UUID,
        *,
        thread_id: UUID,
        user_id: str,
    ) -> AsyncIterator[UUID]:
        """Delete a run by ID."""
        # Get Supabase client
        supabase_client = await get_supabase()

        # Verify thread exists and belongs to user
        thread_result = await (
            supabase_client.table("threads")
            .select("*")
            .eq("thread_id", str(thread_id))
            .eq("user_id", user_id)
            .execute()
        )

        if not thread_result.data:
            return _empty_generator()

        # Delete run from Supabase
        result = await (
            supabase_client.table("runs")
            .delete()
            .eq("run_id", str(run_id))
            .eq("thread_id", str(thread_id))
            .eq("user_id", user_id)
            .execute()
        )

        if not result.data:
            raise HTTPException(status_code=404, detail="Run not found")

        # Delete checkpoints for this run
        # Note: Using conn from connect() for checkpoint operations
        async with connect() as conn:
            _delete_checkpoints_for_thread(thread_id, conn, run_id=run_id)

        async def _yield_deleted():
            await logger.ainfo("Run deleted", run_id=run_id)
            yield run_id

        return _yield_deleted()

    @staticmethod
    async def cancel(
        run_ids: Sequence[UUID | str] | None = None,
        *,
        action: Literal["interrupt", "rollback"] = "interrupt",
        thread_id: UUID | None = None,
        status: Literal["pending", "running", "all"] | None = None,
        user_id: str,
    ) -> None:
        """
        Cancel runs in memory. Must provide either:
        1) thread_id + run_ids, or
        2) status in {"pending", "running", "all"}.

        Steps:
        - Validate arguments (one usage pattern or the other).
        - Gather runs matching either the (thread_id, run_ids) set or the given status.
        - For each run found:
            * Send a cancellation message through the stream manager.
            * If 'pending', set to 'interrupted' or delete (if action='rollback' and not actively queued).
            * If 'running', the worker will pick up the message.
            * Otherwise, log a warning for non-cancelable states.
        - 404 if no runs are found or authorized.
        """
        # Get Supabase client
        supabase_client = await get_supabase()

        # 1. Validate arguments
        if status is not None:
            # If status is set, user must NOT specify thread_id or run_ids
            if thread_id is not None or run_ids is not None:
                raise HTTPException(
                    status_code=422,
                    detail="Cannot specify 'thread_id' or 'run_ids' when using 'status'",
                )
        else:
            # If status is not set, user must specify both thread_id and run_ids
            if thread_id is None or run_ids is None:
                raise HTTPException(
                    status_code=422,
                    detail="Must provide either a status or both 'thread_id' and 'run_ids'",
                )

        status_list: tuple[str, ...] = ()
        if status is not None:
            if status == "all":
                status_list = ("pending", "running")
            elif status in ("pending", "running"):
                status_list = (status,)
            else:
                raise ValueError(f"Unsupported status: {status}")

        # Query runs from Supabase
        query = supabase_client.table("runs").select("*").eq("user_id", user_id)

        if status_list:
            query = query.in_("status", list(status_list))
        else:
            query = query.eq("thread_id", str(thread_id))
            if run_ids:
                query = query.in_("run_id", [str(rid) for rid in run_ids])

        result = await query.execute()
        candidate_runs = result.data or []

        if not candidate_runs:
            raise HTTPException(status_code=404, detail="No runs found to cancel.")

        stream_manager = get_stream_manager()
        coros = []
        cancelable_runs = []

        for run in candidate_runs:
            run_id = run["run_id"]
            run_thread_id = run["thread_id"]
            control_message = Message(
                topic=f"run:{run_id}:control".encode(),
                data=action.encode(),
            )
            coros.append(stream_manager.put(run_id, run_thread_id, control_message))

            queues = stream_manager.get_queues(run_id, run_thread_id)

            if run["status"] in ("pending", "running"):
                cancelable_runs.append(run)
                if queues or action != "rollback":
                    if run["status"] == "pending":
                        # Update thread status to idle
                        await (
                            supabase_client.table("threads")
                            .update(
                                {
                                    "status": "idle",
                                    "updated_at": datetime.now(tz=UTC).isoformat(),
                                }
                            )
                            .eq("thread_id", str(run_thread_id))
                            .eq("user_id", user_id)
                            .execute()
                        )
                    # Update run status to interrupted
                    await (
                        supabase_client.table("runs")
                        .update(
                            {
                                "status": "interrupted",
                                "updated_at": datetime.now(tz=UTC).isoformat(),
                            }
                        )
                        .eq("run_id", str(run_id))
                        .eq("user_id", user_id)
                        .execute()
                    )
                    run["status"] = "interrupted"
                    run["updated_at"] = datetime.now(tz=UTC)
                else:
                    await logger.ainfo(
                        "Eagerly deleting pending run with rollback action",
                        run_id=str(run_id),
                        status=run["status"],
                    )
                    async for _ in Runs.delete(
                        run_id, thread_id=run_thread_id, user_id=user_id
                    ):
                        pass
            else:
                await logger.awarning(
                    "Attempted to cancel non-pending run.",
                    run_id=str(run_id),
                    status=run["status"],
                )

        if not cancelable_runs:
            raise HTTPException(
                status_code=404,
                detail="No matching runs to cancel. Please verify the thread ID and run IDs are correct, and the runs haven't been deleted or completed.",
            )

        if coros:
            await asyncio.gather(*coros)

        await logger.ainfo(
            "Cancelled runs",
            run_ids=[str(r["run_id"]) for r in cancelable_runs],
            thread_id=str(thread_id) if thread_id else None,
            status=status,
            action=action,
        )

    @staticmethod
    async def search(
        thread_id: UUID,
        *,
        user_id: str,
        limit: int = 10,
        offset: int = 0,
        status: RunStatus | None = None,
        select: list[RunSelectField] | None = None,
    ) -> AsyncIterator[Run]:
        """List all runs by thread."""
        # Get Supabase client
        supabase_client = await get_supabase()

        # Build query
        select_fields = "*"
        if select:
            select_fields = ",".join(select)

        query = (
            supabase_client.table("runs")
            .select(select_fields)
            .eq("thread_id", str(thread_id))
            .eq("user_id", user_id)
        )

        if status:
            query = query.eq("status", status)

        query = query.order("created_at", desc=True)

        if limit:
            query = query.limit(limit)
        if offset:
            query = query.offset(offset)

        result = await query.execute()
        runs = result.data or []

        async def _return():
            for run in runs:
                yield run

        return _return()

    @staticmethod
    async def set_status(run_id: UUID, status: RunStatus, *, user_id: str) -> None:
        """Set the status of a run."""
        # Get Supabase client
        supabase_client = await get_supabase()

        # Update run status in Supabase
        result = await (
            supabase_client.table("runs")
            .update({"status": status, "updated_at": datetime.now(tz=UTC).isoformat()})
            .eq("run_id", str(run_id))
            .eq("user_id", user_id)
            .execute()
        )

        if result.data:
            return result.data[0]
        return None

    class Stream:
        @staticmethod
        async def subscribe(
            run_id: UUID,
            thread_id: UUID | None = None,
        ) -> ContextQueue:
            """Subscribe to the run stream, returning a queue."""
            stream_manager = get_stream_manager()
            queue = await stream_manager.add_queue(_ensure_uuid(run_id), thread_id)

            # If there's a control message already stored, send it to the new subscriber
            if thread_id is None:
                thread_id = THREADLESS_KEY
            if control_queues := stream_manager.control_queues.get(thread_id, {}).get(
                run_id
            ):
                for control_queue in control_queues:
                    try:
                        while True:
                            control_msg = control_queue.get()
                            await queue.put(control_msg)
                    except asyncio.QueueEmpty:
                        pass
            return queue

        @staticmethod
        async def join(
            run_id: UUID,
            *,
            stream_channel: asyncio.Queue,
            thread_id: UUID,
            ignore_404: bool = False,
            cancel_on_disconnect: bool = False,
            stream_mode: list[StreamMode] | StreamMode | None = None,
            last_event_id: str | None = None,
            user_id: str,
        ) -> AsyncIterator[tuple[bytes, bytes, bytes | None]]:
            """Stream the run output."""
            from langgraph_api.asyncio import create_task
            from langgraph_api.serde import json_dumpb
            from langgraph_api.utils.stream_codec import decode_stream_message

            queue = stream_channel
            try:
                try:
                    await Runs.Stream.check_run_stream_auth(run_id, thread_id, user_id)
                except HTTPException as e:
                    raise WrappedHTTPException(e) from None

                run_iter = await Runs.get(run_id, thread_id=thread_id, user_id=user_id)
                run = await anext(run_iter, None)

                for message in get_stream_manager().restore_messages(
                    run_id, thread_id, last_event_id
                ):
                    data, id = message.data, message.id
                    decoded = decode_stream_message(data, channel=message.topic)
                    mode = decoded.event_bytes.decode("utf-8")
                    payload = decoded.message_bytes

                    if mode == "control":
                        if payload == b"done":
                            return
                    elif (
                        not stream_mode
                        or mode in stream_mode
                        or (
                            (
                                "messages" in stream_mode
                                or "messages-tuple" in stream_mode
                            )
                            and mode.startswith("messages")
                        )
                    ):
                        yield mode.encode(), payload, id
                        logger.debug(
                            "Replayed run event",
                            run_id=str(run_id),
                            message_id=id,
                            stream_mode=mode,
                            data=data,
                        )

                while True:
                    try:
                        # Wait for messages with a timeout
                        message = await asyncio.wait_for(queue.get(), timeout=0.5)
                        data, id = message.data, message.id
                        decoded = decode_stream_message(data, channel=message.topic)
                        mode = decoded.event_bytes.decode("utf-8")
                        payload = decoded.message_bytes

                        if mode == "control":
                            if payload == b"done":
                                break
                        elif (
                            not stream_mode
                            or mode in stream_mode
                            or (
                                (
                                    "messages" in stream_mode
                                    or "messages-tuple" in stream_mode
                                )
                                and mode.startswith("messages")
                            )
                        ):
                            yield mode.encode(), payload, id
                            logger.debug(
                                "Streamed run event",
                                run_id=str(run_id),
                                stream_mode=mode,
                                message_id=id,
                                data=payload,
                            )
                    except TimeoutError:
                        # Check if the run is still pending
                        run_iter = await Runs.get(
                            run_id, thread_id=thread_id, user_id=user_id
                        )
                        run = await anext(run_iter, None)

                        if ignore_404 and run is None:
                            break
                        elif run is None:
                            yield (
                                b"error",
                                json_dumpb(
                                    HTTPException(
                                        status_code=404, detail="Run not found"
                                    )
                                ),
                                None,
                            )
                            break
                        elif run["status"] not in ("pending", "running"):
                            break
            except WrappedHTTPException as e:
                raise e.http_exception from None
            except:
                if cancel_on_disconnect:
                    async for _ in Runs.cancel(
                        [run_id], thread_id=thread_id, user_id=user_id
                    ):
                        pass
                raise
            finally:
                stream_manager = get_stream_manager()
                await stream_manager.remove_queue(run_id, thread_id, queue)

        @staticmethod
        async def check_run_stream_auth(
            run_id: UUID,
            thread_id: UUID,
            user_id: str,
        ) -> None:
            # Get Supabase client
            supabase_client = await get_supabase()

            # Verify thread exists and belongs to user
            thread_result = await (
                supabase_client.table("threads")
                .select("*")
                .eq("thread_id", str(thread_id))
                .eq("user_id", user_id)
                .execute()
            )

            if not thread_result.data:
                raise HTTPException(status_code=404, detail="Thread not found")

        @staticmethod
        async def publish(
            run_id: UUID | str,
            event: str,
            message: bytes,
            *,
            thread_id: UUID | str | None = None,
            resumable: bool = False,
        ) -> None:
            """Publish a message to all subscribers of the run stream."""
            from langgraph_api.utils.stream_codec import STREAM_CODEC

            topic = f"run:{run_id}:stream".encode()

            stream_manager = get_stream_manager()
            # Send to all queues subscribed to this run_id using protocol frame
            payload = STREAM_CODEC.encode(event, message)
            await stream_manager.put(
                run_id, thread_id, Message(topic=topic, data=payload), resumable
            )
