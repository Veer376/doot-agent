"""Threads service - Business logic for thread operations."""

from __future__ import annotations

import asyncio
import copy
from collections.abc import AsyncIterator, Sequence
from datetime import UTC, datetime
from typing import cast, Any, Literal
from uuid import UUID, uuid4

import orjson
import structlog
from langgraph.checkpoint.serde.jsonplus import _msgpack_ext_hook_to_json
from langgraph.pregel.debug import CheckpointPayload
from langgraph.types import StateSnapshot
from langgraph_sdk import Auth
from starlette.exceptions import HTTPException

from langgraph_runtime_inmem.checkpoint import Checkpointer
from langgraph_runtime_inmem.database import InMemConnectionProto, connect
from langgraph_runtime_inmem.inmem_stream import (
    Message,
    get_stream_manager,
)
from orbit_core.clients import get_supabase

from ...utils import (
    ensure_uuid as _ensure_uuid,
    snapshot_defaults as _snapshot_defaults,
    is_jsonb_contained,
    replace_thread_id as _replace_thread_id,
    patch_interrupt as _patch_interrupt,
    empty_generator as _empty_generator,
    delete_checkpoints_for_thread as _delete_checkpoints_for_thread,
    state_snapshot_to_thread_state,
)

import typing

if typing.TYPE_CHECKING:
    from langgraph_api.config import ThreadTTLConfig
    from langgraph_api.schema import (
        Checkpoint,
        Config,
        MetadataInput,
        MetadataValue,
        OnConflictBehavior,
        RunStatus,
        Thread,
        ThreadSelectField,
        ThreadStatus,
        ThreadStreamMode,
        ThreadUpdateResponse,
    )
    from langgraph_api.utils import AsyncConnectionProto

logger = structlog.stdlib.get_logger(__name__)


class WrappedHTTPException(Exception):
    """Wrapper for HTTPException to allow proper exception handling."""

    def __init__(self, http_exception: HTTPException):
        self.http_exception = http_exception


# Helper function for filter matching
def _check_filter_match(metadata: dict, filters: Auth.types.FilterType | None) -> bool:
    """Check if metadata matches the filter conditions."""
    if not filters:
        return True
    for key, value in filters.items():
        if isinstance(value, dict):
            op = next(iter(value))
            filter_value = value[op]
            if op == "$eq":
                if key not in metadata or metadata[key] != filter_value:
                    return False
            elif op == "$contains":
                if key not in metadata or not isinstance(metadata[key], list):
                    return False
                if isinstance(filter_value, list):
                    for filter_element in filter_value:
                        if filter_element not in metadata[key]:
                            return False
                elif filter_value not in metadata[key]:
                    return False
        else:
            if key not in metadata or metadata[key] != value:
                return False
    return True


class Threads:
    @staticmethod
    async def search(
        conn: InMemConnectionProto,
        *,
        user_id: str,
        ids: list[str] | list[UUID] | None = None,
        metadata: MetadataInput,
        values: MetadataInput,
        status: ThreadStatus | None,
        limit: int,
        offset: int,
        sort_by: str | None = None,
        sort_order: str | None = None,
        select: list[ThreadSelectField] | None = None,
    ) -> tuple[AsyncIterator[Thread], int]:
        metadata = metadata if metadata is not None else {}
        values = values if values is not None else {}

        # Get Supabase client
        supabase_client = await get_supabase()

        # Build query starting with select
        select_fields = "*"
        if select:
            select_fields = ",".join(select)

        query = (
            supabase_client.table("threads")
            .select(select_fields, count="exact")
            .eq("user_id", user_id)
        )

        # Apply filters
        if ids:
            # Ensure all IDs are UUIDs
            uuid_ids = []
            for i in ids:
                try:
                    uuid_ids.append(str(_ensure_uuid(i)))
                except Exception:
                    raise HTTPException(
                        status_code=400, detail="Invalid thread ID " + str(i)
                    ) from None
            query = query.in_("thread_id", uuid_ids)

        if status:
            query = query.eq("status", status)

        # TODO: Implement metadata filtering with JSONB queries
        # if metadata:
        #     for key, value in metadata.items():
        #         query = query.eq(f"metadata->{key}", value)

        # TODO: Implement values filtering with JSONB queries
        # if values:
        #     for key, value in values.items():
        #         query = query.eq(f"values->{key}", value)

        # Apply sorting
        if sort_by and sort_by in ["thread_id", "created_at", "updated_at", "status"]:
            sort_order_str = sort_order.lower() if sort_order else "desc"
            query = query.order(sort_by, desc=(sort_order_str == "desc"))
        else:
            # Default sorting by updated_at in descending order
            query = query.order("updated_at", desc=True)

        # Apply limit and offset
        if limit:
            query = query.limit(limit)
        if offset:
            query = query.offset(offset)

        # Execute query
        result = await query.execute()
        threads = result.data or []
        total_count = result.count if hasattr(result, "count") else len(threads)

        # Calculate cursor
        cursor = offset + limit if total_count > offset + limit else None

        async def thread_iterator() -> AsyncIterator[Thread]:
            for thread in threads:
                yield thread

        return thread_iterator(), cursor

    @staticmethod
    async def _get_with_filters(
        conn: InMemConnectionProto,
        thread_id: UUID,
        user_id: str,
    ) -> Thread | None:
        thread_id = _ensure_uuid(thread_id)

        # Get Supabase client
        supabase_client = await get_supabase()

        # Query thread from Supabase
        result = await (
            supabase_client.table("threads")
            .select("*")
            .eq("thread_id", str(thread_id))
            .eq("user_id", user_id)
            .execute()
        )

        if not result.data:
            return None

        return result.data[0]

    @staticmethod
    async def _get(
        conn: InMemConnectionProto,
        thread_id: UUID,
        user_id: str,
    ) -> Thread | None:
        """Get a thread by ID."""
        return await Threads._get_with_filters(conn, thread_id, user_id)

    @staticmethod
    async def get(
        conn: InMemConnectionProto,
        thread_id: UUID,
        user_id: str,
    ) -> AsyncIterator[Thread]:
        """Get a thread by ID."""
        matching_thread = await Threads._get(conn, thread_id, user_id)

        if not matching_thread:
            raise HTTPException(
                status_code=404, detail=f"Thread with ID {thread_id} not found"
            )

        async def _yield_result():
            if matching_thread:
                yield matching_thread

        return _yield_result()

    @staticmethod
    async def put(
        conn: InMemConnectionProto,
        thread_id: UUID | str,
        *,
        user_id: str,
        metadata: MetadataInput,
        if_exists: OnConflictBehavior,
        ttl: ThreadTTLConfig | None = None,
    ) -> AsyncIterator[Thread]:
        """Insert or update a thread."""
        thread_id = _ensure_uuid(thread_id)
        if metadata is None:
            metadata = {}

        # Get Supabase client
        supabase_client = await get_supabase()

        # Check if thread already exists
        existing_result = await (
            supabase_client.table("threads")
            .select("*")
            .eq("thread_id", str(thread_id))
            .eq("user_id", user_id)
            .execute()
        )

        existing_thread = existing_result.data[0] if existing_result.data else None

        if existing_thread:
            if if_exists == "raise":
                raise HTTPException(
                    status_code=409, detail=f"Thread with ID {thread_id} already exists"
                )
            elif if_exists == "do_nothing":

                async def _yield_existing():
                    yield existing_thread

                return _yield_existing()

        # Create new thread
        now = datetime.now(UTC)
        new_thread: Thread = {
            "thread_id": str(thread_id),
            "created_at": now.isoformat(),
            "updated_at": now.isoformat(),
            "metadata": copy.deepcopy(metadata),
            "status": "idle",
            "values": {},
            "interrupts": {},
        }

        # Insert into Supabase
        result = await (
            supabase_client.table("threads")
            .insert({"user_id": user_id, **new_thread})
            .execute()
        )

        if error := getattr(result, "error", None):
            raise HTTPException(
                status_code=500,
                detail=f"Internal server error: {error} while creating thread",
            )

        inserted_thread = result.data[0] if result.data else new_thread

        async def _yield_new():
            yield inserted_thread

        return _yield_new()

    @staticmethod
    async def patch(
        conn: InMemConnectionProto,
        thread_id: UUID,
        *,
        user_id: str,
        metadata: MetadataValue,
        ttl: ThreadTTLConfig | None = None,
    ) -> AsyncIterator[Thread]:
        """Update a thread."""
        thread_id = _ensure_uuid(thread_id)

        # Get Supabase client
        supabase_client = await get_supabase()

        # Get existing thread
        existing_result = await (
            supabase_client.table("threads")
            .select("*")
            .eq("thread_id", str(thread_id))
            .eq("user_id", user_id)
            .execute()
        )

        if not existing_result.data:
            # Return empty iterator if thread not found
            async def empty_iterator() -> AsyncIterator[Thread]:
                if False:  # This ensures the iterator is empty
                    yield

            return empty_iterator()

        existing_thread = existing_result.data[0]

        # Merge metadata
        existing_metadata = existing_thread.get("metadata", {}) or {}
        merged_metadata = {**existing_metadata, **metadata}

        # Update thread
        update_payload = {
            "metadata": merged_metadata,
            "updated_at": datetime.now(UTC).isoformat(),
        }

        if ttl is not None:
            update_payload["ttl"] = ttl

        result = await (
            supabase_client.table("threads")
            .update(update_payload)
            .eq("thread_id", str(thread_id))
            .eq("user_id", user_id)
            .execute()
        )

        if error := getattr(result, "error", None):
            raise HTTPException(
                status_code=500,
                detail=f"Internal server error: {error} while updating thread",
            )

        updated_thread = (
            result.data[0] if result.data else {**existing_thread, **update_payload}
        )

        async def thread_iterator() -> AsyncIterator[Thread]:
            yield updated_thread

        return thread_iterator()

    @staticmethod
    async def set_status(
        conn: InMemConnectionProto,
        thread_id: UUID,
        checkpoint: CheckpointPayload | None,
        exception: BaseException | None,
        # This does not accept the auth context since it's only used internally
    ) -> None:
        """Set the status of a thread."""
        from langgraph_api.serde import json_dumpb

        thread_id = _ensure_uuid(thread_id)

        async def has_pending_runs(conn_: InMemConnectionProto, tid: UUID) -> bool:
            """Check if thread has any pending runs."""
            # Still using in-memory for runs as we're only updating threads
            return any(
                run["status"] in ("pending", "running") and run["thread_id"] == tid
                for run in conn_.store["runs"]
            )

        # Get Supabase client
        supabase_client = await get_supabase()

        # Find the thread
        thread_result = await (
            supabase_client.table("threads")
            .select("*")
            .eq("thread_id", str(thread_id))
            .execute()
        )

        if not thread_result.data:
            raise HTTPException(
                status_code=404, detail=f"Thread {thread_id} not found."
            )

        # Determine has_next from checkpoint
        has_next = False if checkpoint is None else bool(checkpoint["next"])

        # Determine base status
        if exception:
            status = "error"
        elif has_next:
            status = "interrupted"
        else:
            status = "idle"

        # Check for pending runs and update to busy if found
        if await has_pending_runs(conn, thread_id):
            status = "busy"

        # Update thread in Supabase
        update_payload = {
            "updated_at": datetime.now(UTC).isoformat(),
            "values": checkpoint["values"] if checkpoint else None,
            "status": status,
            "interrupts": (
                {
                    t["id"]: [_patch_interrupt(i) for i in t["interrupts"]]
                    for t in checkpoint["tasks"]
                    if t.get("interrupts")
                }
                if checkpoint
                else {}
            ),
            "error": json_dumpb(exception) if exception else None,
        }

        await (
            supabase_client.table("threads")
            .update(update_payload)
            .eq("thread_id", str(thread_id))
            .execute()
        )

    @staticmethod
    async def set_joint_status(
        conn: InMemConnectionProto,
        thread_id: UUID,
        run_id: UUID,
        run_status: RunStatus | Literal["rollback"],
        graph_id: str,
        checkpoint: CheckpointPayload | None = None,
        exception: BaseException | None = None,
    ) -> None:
        """Set the status of both thread and run atomically in a single query.

        This is an optimized version that combines the logic from Threads.set_status
        and Runs.set_status to minimize database round trips and ensure atomicity.

        Args:
            conn: Database connection
            thread_id: Thread ID to update
            run_id: Run ID to update
            run_status: New status for the run (or "rollback" to delete the run)
            checkpoint: Checkpoint payload for thread status calculation
            exception: Exception that occurred (affects thread status)
        """
        # No auth since it's internal
        from langgraph_api.errors import UserInterrupt, UserRollback
        from langgraph_api.serde import json_dumpb

        thread_id = _ensure_uuid(thread_id)
        run_id = _ensure_uuid(run_id)

        def _thread_has_active_runs() -> bool:
            # Still using in-memory for runs
            return any(
                r["thread_id"] == thread_id and r["status"] in ("pending", "running")
                for r in conn.store["runs"]
            )

        # Get Supabase client
        supabase_client = await get_supabase()

        # Get thread from Supabase
        thread_result = await (
            supabase_client.table("threads")
            .select("*")
            .eq("thread_id", str(thread_id))
            .execute()
        )

        if not thread_result.data:
            raise HTTPException(status_code=404, detail=f"Thread {thread_id} not found")

        thread = thread_result.data[0]

        # Get run from in-memory store (since we're not updating runs table yet)
        run = next(
            (
                r
                for r in conn.store["runs"]
                if r["run_id"] == run_id and r["thread_id"] == thread_id
            ),
            None,
        )
        if run is None:
            raise HTTPException(status_code=404, detail=f"Run {run_id} not found")

        has_next = bool(checkpoint and checkpoint["next"])
        if exception and not isinstance(exception, UserInterrupt | UserRollback):
            base_thread_status: ThreadStatus = "error"
        elif has_next:
            base_thread_status = "interrupted"
        else:
            base_thread_status = "idle"

        interrupts = (
            {
                t["id"]: [_patch_interrupt(i) for i in t["interrupts"]]
                for t in checkpoint["tasks"]
                if t.get("interrupts")
            }
            if checkpoint
            else {}
        )

        now = datetime.now(UTC)

        if run_status == "rollback":
            # Import locally to avoid circular imports
            from .runs import Runs

            await Runs.delete(conn, run_id, thread_id=run["thread_id"])
            final_thread_status: ThreadStatus = (
                "busy" if _thread_has_active_runs() else base_thread_status
            )

        else:
            # Update run in-memory
            run.update({"status": run_status, "updated_at": now})

            if run_status in ("pending", "running") or _thread_has_active_runs():
                final_thread_status = "busy"
            else:
                final_thread_status = base_thread_status

        # Update thread in Supabase
        existing_metadata = thread.get("metadata", {}) or {}
        existing_metadata["graph_id"] = graph_id

        update_payload = {
            "updated_at": now.isoformat(),
            "values": checkpoint["values"] if checkpoint else None,
            "interrupts": interrupts,
            "status": final_thread_status,
            "error": json_dumpb(exception) if exception else None,
            "metadata": existing_metadata,
        }

        await (
            supabase_client.table("threads")
            .update(update_payload)
            .eq("thread_id", str(thread_id))
            .execute()
        )

    @staticmethod
    async def delete(
        conn: InMemConnectionProto,
        thread_id: UUID,
        user_id: str,
    ) -> AsyncIterator[UUID]:
        """Delete a thread by ID and cascade delete all associated runs."""
        thread_id = _ensure_uuid(thread_id)

        # Get Supabase client
        supabase_client = await get_supabase()

        # Delete thread from Supabase
        result = await (
            supabase_client.table("threads")
            .delete()
            .eq("thread_id", str(thread_id))
            .eq("user_id", user_id)
            .execute()
        )

        # If no rows were deleted, thread doesn't exist or doesn't belong to user
        if not result.data:
            raise HTTPException(
                status_code=404, detail=f"Thread with ID {thread_id} not found"
            )

        # Cascade delete all runs associated with this thread (in-memory for now)
        conn.store["runs"] = [
            run for run in conn.store["runs"] if run["thread_id"] != thread_id
        ]

        # Delete checkpoints for this thread
        _delete_checkpoints_for_thread(thread_id, conn)

        # Return an async iterator with the deleted thread_id
        async def id_iterator() -> AsyncIterator[UUID]:
            yield thread_id

        return id_iterator()

    @staticmethod
    async def _delete_with_run(
        conn: InMemConnectionProto,
        thread_id: UUID,
        run_id: UUID,
        user_id: str,
    ) -> UUID:
        """Delete a thread by ID."""
        # We don't really care about "optimal" here.
        # Note: This needs user_id to properly delete from Supabase
        await Threads.delete(conn, thread_id, user_id)
        return thread_id

    @staticmethod
    async def copy(
        conn: InMemConnectionProto,
        thread_id: UUID,
        user_id: str,
    ) -> AsyncIterator[Thread]:
        """Create a copy of an existing thread."""
        thread_id = _ensure_uuid(thread_id)
        new_thread_id = uuid4()

        # Get Supabase client
        supabase_client = await get_supabase()

        async with conn.pipeline():
            # Find the original thread in Supabase
            original_result = await (
                supabase_client.table("threads")
                .select("*")
                .eq("thread_id", str(thread_id))
                .eq("user_id", user_id)
                .execute()
            )

            if not original_result.data:
                return _empty_generator()

            original_thread = original_result.data[0]

            # Create new thread with copied metadata
            now = datetime.now(tz=UTC)
            new_thread: Thread = {
                "thread_id": str(new_thread_id),
                "created_at": now.isoformat(),
                "updated_at": now.isoformat(),
                "metadata": copy.deepcopy(original_thread.get("metadata", {})),
                "status": "idle",
                "values": {},
                "interrupts": {},
            }

            # Insert new thread to Supabase
            result = await (
                supabase_client.table("threads")
                .insert({"user_id": user_id, **new_thread})
                .execute()
            )

            if error := getattr(result, "error", None):
                raise HTTPException(
                    status_code=500,
                    detail=f"Internal server error: {error} while copying thread",
                )

            inserted_thread = result.data[0] if result.data else new_thread

            # Copy checkpoints
            checkpointer = Checkpointer()
            if str(thread_id) in checkpointer.storage:
                copied_storage = _replace_thread_id(
                    checkpointer.storage[str(thread_id)], new_thread_id, thread_id
                )
                checkpointer.storage[str(new_thread_id)] = copied_storage

            # Copy the writes over (if any)
            outer_keys = []
            for k in checkpointer.writes:
                if k[0] == str(thread_id):
                    outer_keys.append(k)
            for tid, checkpoint_ns, checkpoint_id in outer_keys:
                mapped = {
                    k: _replace_thread_id(v, new_thread_id, thread_id)
                    for k, v in checkpointer.writes[
                        (str(tid), checkpoint_ns, checkpoint_id)
                    ].items()
                }

                checkpointer.writes[
                    (str(new_thread_id), checkpoint_ns, checkpoint_id)
                ] = mapped

            # Copy the blobs
            for k in list(checkpointer.blobs):
                if str(k[0]) == str(thread_id):
                    new_key = (str(new_thread_id), *k[1:])
                    checkpointer.blobs[new_key] = checkpointer.blobs[k]

            async def row_generator() -> AsyncIterator[Thread]:
                yield inserted_thread

            return row_generator()

    @staticmethod
    async def sweep_ttl(
        conn: InMemConnectionProto,
        *,
        limit: int | None = None,
        batch_size: int = 100,
    ) -> tuple[int, int]:
        # Not implemented for inmem server
        return (0, 0)

    class State:
        # We will treat this like a runs resource for now.
        resource = "threads"

        @staticmethod
        async def get(
            conn: InMemConnectionProto,
            config: Config,
            subgraphs: bool = False,
            ctx: Auth.types.BaseAuthContext | None = None,
        ) -> StateSnapshot:
            """Get state for a thread."""
            from langgraph_api.graph import get_graph
            from langgraph_api.store import get_store

            checkpointer = await asyncio.to_thread(
                Checkpointer, conn, unpack_hook=_msgpack_ext_hook_to_json
            )
            thread_id = _ensure_uuid(config["configurable"]["thread_id"])
            # Auth will be applied here so no need to use filters downstream
            thread_iter = await Threads.get(conn, thread_id, ctx=ctx)
            thread = await anext(thread_iter)
            checkpoint = await checkpointer.aget(config)

            if not thread:
                return StateSnapshot(
                    values={},
                    next=[],
                    config=None,
                    metadata=None,
                    created_at=None,
                    parent_config=None,
                    tasks=tuple(),
                    **_snapshot_defaults(),
                )

            metadata = thread.get("metadata", {})
            thread_config = cast(dict[str, Any], thread.get("config", {}))
            thread_config = {
                **thread_config,
                "configurable": {
                    **thread_config.get("configurable", {}),
                    **config.get("configurable", {}),
                },
            }

            # Fallback to graph_id from run if not in thread metadata
            graph_id = metadata.get("graph_id")
            if not graph_id:
                for run in conn.store["runs"]:
                    if run["thread_id"] == thread_id:
                        graph_id = run["kwargs"]["config"]["configurable"]["graph_id"]
                        break

            if graph_id:
                # format latest checkpoint for response
                checkpointer.latest_iter = checkpoint
                async with get_graph(
                    graph_id,
                    thread_config,
                    checkpointer=checkpointer,
                    store=(await get_store()),
                ) as graph:
                    result = await graph.aget_state(config, subgraphs=subgraphs)
                    if (
                        result.metadata is not None
                        and "checkpoint_ns" in result.metadata
                        and result.metadata["checkpoint_ns"] == ""
                    ):
                        result.metadata.pop("checkpoint_ns")
                    return result
            else:
                return StateSnapshot(
                    values={},
                    next=[],
                    config=None,
                    metadata=None,
                    created_at=None,
                    parent_config=None,
                    tasks=tuple(),
                    **_snapshot_defaults(),
                )

        @staticmethod
        async def post(
            conn: InMemConnectionProto,
            config: Config,
            values: Sequence[dict] | dict[str, Any] | None,
            as_node: str | None = None,
            ctx: Auth.types.BaseAuthContext | None = None,
        ) -> ThreadUpdateResponse:
            """Add state to a thread."""
            from langgraph_api.graph import get_graph
            from langgraph_api.schema import ThreadUpdateResponse
            from langgraph_api.store import get_store
            from langgraph_api.utils import fetchone

            thread_id = _ensure_uuid(config["configurable"]["thread_id"])
            filters = await Threads.handle_event(
                ctx,
                "update",
                Auth.types.ThreadsUpdate(thread_id=thread_id),
            )

            checkpointer = Checkpointer()

            thread_iter = await Threads.get(conn, thread_id, ctx=ctx)
            thread = await fetchone(
                thread_iter, not_found_detail=f"Thread {thread_id} not found."
            )
            checkpoint = await checkpointer.aget(config)

            if not thread:
                raise HTTPException(status_code=404, detail="Thread not found")
            if not _check_filter_match(thread["metadata"], filters):
                raise HTTPException(status_code=403, detail="Forbidden")

            metadata = thread["metadata"]
            thread_config = thread["config"]
            # Check that there are no in-flight runs
            pending_runs = [
                run
                for run in conn.store["runs"]
                if run["thread_id"] == thread_id
                and run["status"] in ("pending", "running")
            ]
            if pending_runs:
                raise HTTPException(
                    status_code=409,
                    detail=f"Thread {thread_id} has in-flight runs: {pending_runs}",
                )
            thread_config = {
                **thread_config,
                "configurable": {
                    **thread_config.get("configurable", {}),
                    **config.get("configurable", {}),
                },
            }

            # Fallback to graph_id from run if not in thread metadata
            graph_id = metadata.get("graph_id")
            if not graph_id:
                for run in conn.store["runs"]:
                    if run["thread_id"] == thread_id:
                        graph_id = run["kwargs"]["config"]["configurable"]["graph_id"]
                        break

            if graph_id:
                config["configurable"].setdefault("graph_id", graph_id)

                checkpointer.latest_iter = checkpoint
                async with get_graph(
                    graph_id,
                    thread_config,
                    checkpointer=checkpointer,
                    store=(await get_store()),
                ) as graph:
                    update_config = config.copy()
                    update_config["configurable"] = {
                        **config["configurable"],
                        "checkpoint_ns": config["configurable"].get(
                            "checkpoint_ns", ""
                        ),
                    }
                    next_config = await graph.aupdate_state(
                        update_config, values, as_node=as_node
                    )

                    # Get current state
                    state = await Threads.State.get(
                        conn, config, subgraphs=False, ctx=ctx
                    )
                    # Update thread values
                    for thread in conn.store["threads"]:
                        if thread["thread_id"] == thread_id:
                            thread["values"] = state.values
                            break

                    # Publish state update event
                    from langgraph_api.serde import json_dumpb

                    event_data = {
                        "state": state,
                        "thread_id": str(thread_id),
                    }
                    await Threads.Stream.publish(
                        thread_id,
                        "state_update",
                        json_dumpb(event_data),
                    )

                    return ThreadUpdateResponse(
                        checkpoint=next_config["configurable"],
                        # Including deprecated fields
                        configurable=next_config["configurable"],
                        checkpoint_id=next_config["configurable"]["checkpoint_id"],
                    )
            else:
                raise HTTPException(
                    status_code=400,
                    detail=f"Thread '{thread['thread_id']}' has no assigned graph ID. This usually occurs when no runs have been made on this particular thread."
                    " This operation requires a graph ID. Please ensure a run has been made for the thread or manually update the thread metadata (by setting the 'graph_id' field) before running this operation.",
                )

        @staticmethod
        async def bulk(
            conn: InMemConnectionProto,
            *,
            config: Config,
            supersteps: Sequence[dict],
            ctx: Auth.types.BaseAuthContext | None = None,
        ) -> ThreadUpdateResponse:
            """Update a thread with a batch of state updates."""

            from langgraph.types import StateUpdate
            from langgraph_api.command import map_cmd
            from langgraph_api.graph import get_graph
            from langgraph_api.schema import ThreadUpdateResponse
            from langgraph_api.store import get_store
            from langgraph_api.utils import fetchone

            thread_id = _ensure_uuid(config["configurable"]["thread_id"])
            filters = await Threads.handle_event(
                ctx,
                "update",
                Auth.types.ThreadsUpdate(thread_id=thread_id),
            )

            thread_iter = await Threads.get(conn, thread_id, ctx=ctx)
            thread = await fetchone(
                thread_iter, not_found_detail=f"Thread {thread_id} not found."
            )

            thread_config = cast(dict[str, Any], thread["config"])
            thread_config = {
                **thread_config,
                "configurable": {
                    **thread_config.get("configurable", {}),
                    **config.get("configurable", {}),
                },
            }
            metadata = thread["metadata"]

            if not thread:
                raise HTTPException(status_code=404, detail="Thread not found")

            if not _check_filter_match(metadata, filters):
                raise HTTPException(status_code=403, detail="Forbidden")

            if graph_id := metadata.get("graph_id"):
                config["configurable"].setdefault("graph_id", graph_id)
                config["configurable"].setdefault("checkpoint_ns", "")

                async with get_graph(
                    graph_id,
                    thread_config,
                    checkpointer=Checkpointer(),
                    store=(await get_store()),
                ) as graph:
                    next_config = await graph.abulk_update_state(
                        config,
                        [
                            [
                                StateUpdate(
                                    (
                                        map_cmd(update.get("command"))
                                        if update.get("command")
                                        else update.get("values")
                                    ),
                                    update.get("as_node"),
                                )
                                for update in superstep.get("updates", [])
                            ]
                            for superstep in supersteps
                        ],
                    )

                    state = await Threads.State.get(
                        conn, config, subgraphs=False, ctx=ctx
                    )

                    # update thread values
                    for thread in conn.store["threads"]:
                        if thread["thread_id"] == thread_id:
                            thread["values"] = state.values
                            break

                    # Publish state update event
                    from langgraph_api.serde import json_dumpb

                    event_data = {
                        "state": state,
                        "thread_id": str(thread_id),
                    }
                    await Threads.Stream.publish(
                        thread_id,
                        "state_update",
                        json_dumpb(event_data),
                    )

                    return ThreadUpdateResponse(
                        checkpoint=next_config["configurable"],
                    )
            else:
                raise HTTPException(
                    status_code=400,
                    detail=f"Thread '{thread['thread_id']}' has no assigned graph ID. This usually occurs when no runs have been made on this particular thread."
                    " This operation requires a graph ID. Please ensure a run has been made for the thread or manually update the thread metadata (by setting the 'graph_id' field) before running this operation.",
                )

        @staticmethod
        async def list(
            conn: InMemConnectionProto,
            *,
            config: Config,
            limit: int = 1,
            before: str | Checkpoint | None = None,
            metadata: MetadataInput = None,
            ctx: Auth.types.BaseAuthContext | None = None,
        ) -> list[StateSnapshot]:
            """Get the history of a thread."""
            from langgraph_api.graph import get_graph
            from langgraph_api.store import get_store
            from langgraph_api.utils import fetchone

            thread_id = _ensure_uuid(config["configurable"]["thread_id"])
            thread = None
            filters = await Threads.handle_event(
                ctx,
                "read",
                Auth.types.ThreadsRead(thread_id=thread_id),
            )
            thread = await fetchone(
                await Threads.get(conn, config["configurable"]["thread_id"], ctx=ctx)
            )

            # Parse thread metadata and config
            thread_metadata = thread["metadata"]
            if not _check_filter_match(thread_metadata, filters):
                return []

            thread_config = cast(dict[str, Any], thread["config"])
            thread_config = {
                **thread_config,
                "configurable": {
                    **thread_config.get("configurable", {}),
                    **config.get("configurable", {}),
                },
            }
            # If graph_id exists, get state history
            if graph_id := thread_metadata.get("graph_id"):
                async with get_graph(
                    graph_id,
                    thread_config,
                    checkpointer=await asyncio.to_thread(
                        Checkpointer, conn, unpack_hook=_msgpack_ext_hook_to_json
                    ),
                    store=(await get_store()),
                ) as graph:
                    # Convert before parameter if it's a string
                    before_param = (
                        {"configurable": {"checkpoint_id": before}}
                        if isinstance(before, str)
                        else before
                    )

                    states = [
                        state
                        async for state in graph.aget_state_history(
                            config, limit=limit, filter=metadata, before=before_param
                        )
                    ]

                    return states

            return []

    class Stream:
        @staticmethod
        async def subscribe(
            conn: InMemConnectionProto | AsyncConnectionProto,
            thread_id: UUID,
            seen_runs: set[UUID],
        ) -> list[tuple[UUID, asyncio.Queue]]:
            """Subscribe to the thread stream, creating queues for unseen runs."""
            stream_manager = get_stream_manager()
            queues = []

            # Create new queues only for runs not yet seen
            thread_id = _ensure_uuid(thread_id)

            # Add thread stream queue
            if thread_id not in seen_runs:
                queue = await stream_manager.add_thread_stream(thread_id)
                queues.append((thread_id, queue))
                seen_runs.add(thread_id)

            for run in conn.store["runs"]:
                if run["thread_id"] == thread_id:
                    run_id = run["run_id"]
                    if run_id not in seen_runs:
                        queue = await stream_manager.add_queue(run_id, thread_id)
                        queues.append((run_id, queue))
                        seen_runs.add(run_id)

            return queues

        @staticmethod
        async def join(
            thread_id: UUID,
            *,
            last_event_id: str | None = None,
            stream_modes: list[ThreadStreamMode],
        ) -> AsyncIterator[tuple[bytes, bytes, bytes | None]]:
            """Stream the thread output."""
            from langgraph_api.utils.stream_codec import (
                decode_stream_message,
            )

            def should_filter_event(event_name: str, message_bytes: bytes) -> bool:
                """Check if an event should be filtered out based on stream_modes."""
                if "run_modes" in stream_modes and event_name != "state_update":
                    return False
                if "state_update" in stream_modes and event_name == "state_update":
                    return False
                if "lifecycle" in stream_modes and event_name == "metadata":
                    try:
                        message_data = orjson.loads(message_bytes)
                        if message_data.get("status") == "run_done":
                            return False
                        if "attempt" in message_data and "run_id" in message_data:
                            return False
                    except (orjson.JSONDecodeError, TypeError):
                        pass
                return True

            stream_manager = get_stream_manager()
            seen_runs: set[UUID] = set()
            created_queues: list[tuple[UUID, asyncio.Queue]] = []

            try:
                async with connect() as conn:
                    await logger.ainfo(
                        "Joined thread stream",
                        thread_id=str(thread_id),
                    )

                    # Restore messages if resuming from a specific event
                    if last_event_id is not None:
                        # Collect all events from all message stores for this thread
                        all_events = []
                        for run_id in stream_manager.message_stores.get(
                            str(thread_id), []
                        ):
                            for message in stream_manager.restore_messages(
                                run_id, thread_id, last_event_id
                            ):
                                all_events.append((message, run_id))

                        # Sort by message ID (which is ms-seq format)
                        all_events.sort(key=lambda x: x[0].id.decode())

                        # Yield sorted events
                        for message, run_id in all_events:
                            decoded = decode_stream_message(
                                message.data, channel=message.topic
                            )
                            event_bytes = decoded.event_bytes
                            message_bytes = decoded.message_bytes

                            if event_bytes == b"control":
                                if message_bytes == b"done":
                                    event_bytes = b"metadata"
                                    message_bytes = orjson.dumps(
                                        {"status": "run_done", "run_id": run_id}
                                    )
                            if not should_filter_event(
                                event_bytes.decode("utf-8"), message_bytes
                            ):
                                yield (
                                    event_bytes,
                                    message_bytes,
                                    message.id,
                                )

                    # Listen for live messages from all queues
                    while True:
                        # Refresh queues to pick up any new runs that joined this thread
                        new_queue_tuples = await Threads.Stream.subscribe(
                            conn, thread_id, seen_runs
                        )
                        # Track new queues for cleanup
                        for run_id, queue in new_queue_tuples:
                            created_queues.append((run_id, queue))

                        for run_id, queue in created_queues:
                            try:
                                message = await asyncio.wait_for(
                                    queue.get(), timeout=0.2
                                )
                                decoded = decode_stream_message(
                                    message.data, channel=message.topic
                                )
                                event = decoded.event_bytes
                                event_name = event.decode("utf-8")
                                payload = decoded.message_bytes

                                if event == b"control" and payload == b"done":
                                    topic = message.topic.decode()
                                    run_id = topic.split("run:")[1].split(":")[0]
                                    meta_event = b"metadata"
                                    meta_payload = orjson.dumps(
                                        {"status": "run_done", "run_id": run_id}
                                    )
                                    if not should_filter_event(
                                        "metadata", meta_payload
                                    ):
                                        yield (meta_event, meta_payload, message.id)
                                else:
                                    if not should_filter_event(event_name, payload):
                                        yield (event, payload, message.id)

                            except TimeoutError:
                                continue
                            except (ValueError, KeyError):
                                continue

                        # Yield execution to other tasks to prevent event loop starvation
                        await asyncio.sleep(0)

            except WrappedHTTPException as e:
                raise e.http_exception from None
            except asyncio.CancelledError:
                await logger.awarning(
                    "Thread stream client disconnected",
                    thread_id=str(thread_id),
                )
                raise
            except:
                raise
            finally:
                # Clean up all created queues
                for run_id, queue in created_queues:
                    try:
                        await stream_manager.remove_queue(run_id, thread_id, queue)
                    except Exception:
                        # Ignore cleanup errors
                        pass

        @staticmethod
        async def publish(
            thread_id: UUID | str,
            event: str,
            message: bytes,
        ) -> None:
            """Publish a thread-level event to the thread stream."""
            from langgraph_api.utils.stream_codec import STREAM_CODEC

            topic = f"thread:{thread_id}:stream".encode()

            stream_manager = get_stream_manager()
            payload = STREAM_CODEC.encode(event, message)
            await stream_manager.put_thread(
                str(thread_id), Message(topic=topic, data=payload)
            )

    @staticmethod
    async def count(
        conn: InMemConnectionProto,
        *,
        user_id: str,
        metadata: MetadataInput = None,
        values: MetadataInput = None,
        status: ThreadStatus | None = None,
    ) -> int:
        """Get count of threads."""
        metadata = metadata if metadata is not None else {}
        values = values if values is not None else {}

        # Get Supabase client
        supabase_client = await get_supabase()

        # Build query
        query = (
            supabase_client.table("threads")
            .select("*", count="exact")
            .eq("user_id", user_id)
        )

        if status:
            query = query.eq("status", status)

        # TODO: Implement metadata filtering with JSONB queries
        # TODO: Implement values filtering with JSONB queries

        # Execute query
        result = await query.execute()

        return result.count if hasattr(result, "count") else 0
