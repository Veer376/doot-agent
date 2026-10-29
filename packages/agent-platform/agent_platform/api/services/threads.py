"""Threads service - Business logic for thread operations."""

from __future__ import annotations

import asyncio
import copy
from collections.abc import AsyncIterator, Sequence
from datetime import UTC, datetime
from typing import cast, Any, Literal, TypedDict
from uuid import UUID, uuid4

import orjson
import structlog

from langgraph.pregel.debug import CheckpointPayload
from langgraph.types import StateSnapshot
from langgraph_sdk import Auth
from starlette.exceptions import HTTPException

from langgraph_sdk.schema import Checkpoint
from orbit_core.clients import get_supabase
from orbit_core.clients import get_checkpointer
from orbit_core.clients import get_store
from ...graph import get_graph

from ...utils import (
    ensure_uuid as _ensure_uuid,
    snapshot_defaults as _snapshot_defaults,
    replace_thread_id as _replace_thread_id,
    patch_interrupt as _patch_interrupt,
    state_snapshot_to_thread_state,
)

import typing

from langgraph_sdk.schema import (
    Checkpoint,
    Config,
    RunStatus,
    Thread, 
    ThreadSelectField,
    ThreadStatus,
    ThreadStreamMode,
    OnConflictBehavior,
)

logger = structlog.stdlib.get_logger(__name__)

class ThreadTTLConfig(TypedDict, total=False):
    strategy: Literal["delete"]
    default_ttl: float | None
    sweep_interval_minutes: int | None

MetadataInput = dict[str, Any] | None
MetadataValue = dict[str, Any]


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
    ) -> tuple[list[Thread], int]:
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

        return threads, cursor

    @staticmethod
    async def _get_with_filters(
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
        thread_id: UUID,
        user_id: str,
    ) -> Thread | None:
        """Get a thread by ID."""
        return await Threads._get_with_filters(thread_id, user_id)

    @staticmethod
    async def get(
        thread_id: UUID,
        user_id: str,
    ) -> Thread:
        """Get a thread by ID."""
        matching_thread = await Threads._get(thread_id, user_id)

        if not matching_thread:
            raise HTTPException(
                status_code=404, detail=f"Thread with ID {thread_id} not found"
            )

        return matching_thread

    @staticmethod
    async def put(
        thread_id: UUID | str,
        *,
        user_id: str,
        metadata: MetadataInput,
        if_exists: OnConflictBehavior,
        ttl: ThreadTTLConfig | None = None,
    ) -> Thread:
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
                return existing_thread

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

        return inserted_thread

    @staticmethod
    async def patch(
        thread_id: UUID,
        *,
        user_id: str,
        metadata: MetadataValue,
        ttl: ThreadTTLConfig | None = None,
    ) -> Thread | None:
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
            # Return None if thread not found
            return None

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

        return updated_thread

    @staticmethod
    async def set_status(
        thread_id: UUID,
        checkpoint: CheckpointPayload | None,
        exception: BaseException | None,
        # This does not accept the auth context since it's only used internally
    ) -> None:
        """Set the status of a thread."""
        from langgraph_api.serde import json_dumpb

        thread_id = _ensure_uuid(thread_id)

        async def has_pending_runs(tid: UUID) -> bool:
            """Check if thread has any pending runs."""
            # Still using in-memory for runs as we're only updating threads
            from langgraph_runtime_inmem.database import connect
            
            async with connect() as conn_:
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
        if await has_pending_runs(thread_id):
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
        from langgraph_runtime_inmem.database import connect

        thread_id = _ensure_uuid(thread_id)
        run_id = _ensure_uuid(run_id)

        async def _thread_has_active_runs() -> bool:
            # Still using in-memory for runs
            async with connect() as conn_:
                return any(
                    r["thread_id"] == thread_id and r["status"] in ("pending", "running")
                    for r in conn_.store["runs"]
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
        async with connect() as conn_:
            run = next(
                (
                    r
                    for r in conn_.store["runs"]
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

            # For rollback, we need to get user_id from thread
            # Runs.delete requires user_id, so we pass thread's user_id
            # Note: This assumes run belongs to same user as thread
            async with connect() as conn_:
                # Delete from in-memory store
                await Runs.delete(run_id, thread_id=run["thread_id"], user_id=thread.get("user_id"))
            
            final_thread_status: ThreadStatus = (
                "busy" if await _thread_has_active_runs() else base_thread_status
            )

        else:
            # Update run in-memory
            async with connect() as conn_:
                for r in conn_.store["runs"]:
                    if r["run_id"] == run_id and r["thread_id"] == thread_id:
                        r.update({"status": run_status, "updated_at": now})
                        break

            if run_status in ("pending", "running") or await _thread_has_active_runs():
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
        thread_id: str,
        user_id: str,
    ) -> UUID:
        """Delete a thread by ID and cascade delete all associated runs."""

        supabase_client = await get_supabase()

        # Delete thread from Supabase
        result = await (
            supabase_client.table("threads")
            .delete()
            .eq("thread_id", thread_id)
            .eq("user_id", user_id)
            .execute()
        )
        
        # If no rows were deleted, thread doesn't exist or doesn't belong to user
        if not result.data:
            raise HTTPException(
                status_code=404, detail=f"Thread with ID {thread_id} not found"
            )
            
        checkpointer = get_checkpointer()
        await checkpointer.adelete_thread(thread_id)
        
        return thread_id

    @staticmethod
    async def delete_from_checkpoint(
        thread_id: str,
        checkpoint_id: str,
        user_id: str,
    ) -> None:
        """Delete all checkpoints from a specific checkpoint onwards (including the checkpoint itself).
        This effectively rolls back the thread to the parent of the specified checkpoint.
        """
        supabase_client = await get_supabase()
        
        # First verify the thread belongs to the user
        thread_result = await (
            supabase_client.table("threads")
            .select("thread_id")
            .eq("thread_id", thread_id)
            .eq("user_id", user_id)
            .execute()
        )
        
        if not thread_result.data:
            raise HTTPException(
                status_code=404, 
                detail=f"Thread with ID {thread_id} not found"
            )
        
        checkpointer = get_checkpointer()
        
        # Use recursive CTE to find all descendant checkpoints
        # Then delete them from all checkpoint tables
        async with checkpointer._cursor(pipeline=True) as cur:
            # Find all checkpoint IDs to delete (the target checkpoint and all its descendants)
            await cur.execute(
                """
                WITH RECURSIVE checkpoint_tree AS (
                    -- Base case: the checkpoint we want to delete
                    SELECT checkpoint_id, thread_id, checkpoint_ns, parent_checkpoint_id
                    FROM checkpoints
                    WHERE thread_id = %s AND checkpoint_id = %s
                    
                    UNION ALL
                    
                    -- Recursive case: find all children
                    SELECT c.checkpoint_id, c.thread_id, c.checkpoint_ns, c.parent_checkpoint_id
                    FROM checkpoints c
                    INNER JOIN checkpoint_tree ct ON c.parent_checkpoint_id = ct.checkpoint_id 
                        AND c.thread_id = ct.thread_id
                        AND c.checkpoint_ns = ct.checkpoint_ns
                )
                DELETE FROM checkpoint_writes
                WHERE (thread_id, checkpoint_ns, checkpoint_id) IN (
                    SELECT thread_id, checkpoint_ns, checkpoint_id FROM checkpoint_tree
                )
                """,
                (str(thread_id), checkpoint_id),
            )
            
            await cur.execute(
                """
                WITH RECURSIVE checkpoint_tree AS (
                    SELECT checkpoint_id, thread_id, checkpoint_ns, parent_checkpoint_id
                    FROM checkpoints
                    WHERE thread_id = %s AND checkpoint_id = %s
                    
                    UNION ALL
                    
                    SELECT c.checkpoint_id, c.thread_id, c.checkpoint_ns, c.parent_checkpoint_id
                    FROM checkpoints c
                    INNER JOIN checkpoint_tree ct ON c.parent_checkpoint_id = ct.checkpoint_id 
                        AND c.thread_id = ct.thread_id
                        AND c.checkpoint_ns = ct.checkpoint_ns
                )
                DELETE FROM checkpoint_blobs
                WHERE (thread_id, checkpoint_ns) IN (
                    SELECT DISTINCT thread_id, checkpoint_ns FROM checkpoint_tree
                )
                AND version > (
                    SELECT MIN(checkpoint_id) FROM checkpoint_tree WHERE thread_id = %s
                )
                """,
                (str(thread_id), checkpoint_id, str(thread_id)),
            )
            
            await cur.execute(
                """
                WITH RECURSIVE checkpoint_tree AS (
                    SELECT checkpoint_id, thread_id, checkpoint_ns, parent_checkpoint_id
                    FROM checkpoints
                    WHERE thread_id = %s AND checkpoint_id = %s
                    
                    UNION ALL
                    
                    SELECT c.checkpoint_id, c.thread_id, c.checkpoint_ns, c.parent_checkpoint_id
                    FROM checkpoints c
                    INNER JOIN checkpoint_tree ct ON c.parent_checkpoint_id = ct.checkpoint_id 
                        AND c.thread_id = ct.thread_id
                        AND c.checkpoint_ns = ct.checkpoint_ns
                )
                DELETE FROM checkpoints
                WHERE (thread_id, checkpoint_ns, checkpoint_id) IN (
                    SELECT thread_id, checkpoint_ns, checkpoint_id FROM checkpoint_tree
                )
                """,
                (str(thread_id), checkpoint_id),
            )
        
        logger.info(f"Deleted checkpoints from {checkpoint_id} onwards for thread {thread_id}")

    @staticmethod
    async def _delete_with_run(
        thread_id: UUID,
        run_id: UUID,
        user_id: str,
    ) -> UUID:
        """Delete a thread by ID."""
        # We don't really care about "optimal" here.
        # Note: This needs user_id to properly delete from Supabase
        await Threads.delete(thread_id, user_id)
        return thread_id

    @staticmethod
    async def copy(
        thread_id: UUID,
        user_id: str,
    ) -> Thread | None:
        """Create a copy of an existing thread."""
        thread_id = _ensure_uuid(thread_id)
        new_thread_id = uuid4()

        # Get Supabase client
        supabase_client = await get_supabase()

        # Find the original thread in Supabase
        original_result = await (
            supabase_client.table("threads")
            .select("*")
            .eq("thread_id", str(thread_id))
            .eq("user_id", user_id)
            .execute()
        )

        if not original_result.data:
            return None

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

        # Copy checkpoints using the configured checkpointer
        checkpointer = get_checkpointer()
        
        
        # If an in-memory checkpointer is in use, preserve existing behavior
        if hasattr(checkpointer, "storage"):
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
        elif True:
            # For AsyncPostgresSaver, directly copy checkpoint data from database tables
            # This is similar to how adelete_thread works but copies instead of deleting
            try:
                async with checkpointer._cursor(pipeline=True) as cur:
                    # Copy checkpoints table
                    await cur.execute(
                        """
                        INSERT INTO checkpoints (thread_id, checkpoint_ns, checkpoint_id, parent_checkpoint_id, type, checkpoint, metadata)
                        SELECT %s, checkpoint_ns, checkpoint_id, parent_checkpoint_id, type, checkpoint, metadata
                        FROM checkpoints
                        WHERE thread_id = %s
                        """,
                        (str(new_thread_id), str(thread_id)),
                    )
                    # Copy checkpoint_blobs table
                    await cur.execute(
                        """
                        INSERT INTO checkpoint_blobs (thread_id, checkpoint_ns, channel, version, type, blob)
                        SELECT %s, checkpoint_ns, channel, version, type, blob
                        FROM checkpoint_blobs
                        WHERE thread_id = %s
                        """,
                        (str(new_thread_id), str(thread_id)),
                    )
                    # Copy checkpoint_writes table
                    await cur.execute(
                        """
                        INSERT INTO checkpoint_writes (thread_id, checkpoint_ns, checkpoint_id, task_id, idx, channel, type, blob)
                        SELECT %s, checkpoint_ns, checkpoint_id, task_id, idx, channel, type, blob
                        FROM checkpoint_writes
                        WHERE thread_id = %s
                        """,
                        (str(new_thread_id), str(thread_id)),
                    )
                
                logger.info(f"Successfully copied checkpoint data from {thread_id} to {new_thread_id}")
                
            except Exception as e:
                logger.error(f"Failed to copy checkpoint data: {str(e)}", error=str(e))
                
        else:
            try:
                async for tpl in checkpointer.alist(
                    None, filter={"thread_id": str(thread_id)}
                ):
                    # tpl is a CheckpointTuple with fields: config, checkpoint, metadata, parent_config, pending_writes
                    new_config = copy.deepcopy(tpl.config)
                    if not new_config.get("configurable"):
                        new_config["configurable"] = {}
                    new_config["configurable"]["thread_id"] = str(new_thread_id)

                    new_metadata = dict(tpl.metadata or {})
                    # mark as forked copy
                    new_metadata.setdefault("source", "fork")

                    # Use checkpoint's channel_versions as new_versions
                    new_versions = tpl.checkpoint.get("channel_versions", {})

                    await checkpointer.aput(new_config, tpl.checkpoint, new_metadata, new_versions)

                    if getattr(tpl, "pending_writes", None):
                        # pending_writes is a list of (channel, key, value) tuples in some implementations;
                        # attempt a reasonable mapping to put_writes. If this fails, ignore writes copy.
                        try:
                            writes = [(w[1], w[2]) for w in tpl.pending_writes]
                            await checkpointer.aput_writes(new_config, writes, task_id=tpl.checkpoint.get("id", "copied"))
                        except Exception:
                            # ignore writes copy errors
                            pass
            except Exception as e:
                logger.error(f"Failed to copy checkpoint data: {str(e)}", error=str(e))
                
        return inserted_thread

    @staticmethod
    async def sweep_ttl(
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
            config: Config,
            user_id: str,
            subgraphs: bool = False,
        ) -> StateSnapshot:
            """Get state for a thread."""

            checkpointer = get_checkpointer()
            thread_id = config["configurable"]["thread_id"]
            
            thread = await Threads.get(thread_id, user_id=user_id)
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

            metadata = thread.get("metadata", {}) or {}
            thread_config = thread.get("config") or {}
            thread_config = {
                **thread_config,
                "configurable": {
                    **thread_config.get("configurable", {}),
                    **config.get("configurable", {}),
                },
            }

            # Fallback to graph_id from run if not in thread metadata
            assistant_id = metadata.get("assistant_id")
            
            # For now the graph_id = assistant_id
            # graph_id = metadata.get("graph_id")
            # if not graph_id:
            #     from langgraph_runtime_inmem.database import connect
            #     async with connect() as conn_:
            #         for run in conn_.store["runs"]:
            #             if run["thread_id"] == thread_id:
            #                 graph_id = run["kwargs"]["config"]["configurable"]["graph_id"]
            #                 break
            
            graph_id = assistant_id # later we will pass the signature. <assistant_id:graph_id>
            
            if graph_id:
                # checkpointer.latest_iter = checkpoint
                graph = await get_graph(
                            graph_id,
                            thread_config,
                            checkpointer=checkpointer,
                            store=get_store(),
                        )
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

            from langgraph_runtime_inmem.database import connect
            
            checkpointer = Checkpointer()

            thread_iter = await Threads.get(thread_id, user_id=ctx.get("user_id") if ctx else "")
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
            async with connect() as conn_:
                pending_runs = [
                    run
                    for run in conn_.store["runs"]
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
                async with connect() as conn_:
                    for run in conn_.store["runs"]:
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
                    store=get_store(),
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
                        config, subgraphs=False, ctx=ctx
                    )
                    # Update thread values in Supabase
                    supabase_client = await get_supabase()
                    await (
                        supabase_client.table("threads")
                        .update({"values": state.values})
                        .eq("thread_id", str(thread_id))
                        .execute()
                    )

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
            *,
            config: Config,
            user_id: str,
            supersteps: Sequence[dict],
        ) -> ThreadUpdateResponse:
            """Update a thread with a batch of state updates."""

            from langgraph.types import StateUpdate
            from langgraph_api.command import map_cmd
            from langgraph_api.graph import get_graph
            from langgraph_api.schema import ThreadUpdateResponse
            from langgraph_api.store import get_store

            thread_id = _ensure_uuid(config["configurable"]["thread_id"])

            thread = await Threads.get(thread_id, user_id=user_id)

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

            if graph_id := metadata.get("graph_id"):
                config["configurable"].setdefault("graph_id", graph_id)
                config["configurable"].setdefault("checkpoint_ns", "")

                async with get_graph(
                    graph_id,
                    thread_config,
                    checkpointer=get_checkpointer(),
                    store=get_store(),
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
                        config, subgraphs=False, ctx=ctx
                    )

                    # Update thread values in Supabase
                    supabase_client = await get_supabase()
                    await (
                        supabase_client.table("threads")
                        .update({"values": state.values})
                        .eq("thread_id", str(thread_id))
                        .execute()
                    )

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
            *,
            config: Config,
            user_id: str,
            limit: int = 1,
            before: str | Checkpoint | None = None,
            metadata: MetadataInput = None,
        ) -> list[StateSnapshot]:
            """Get the history of a thread."""
            
            thread_id = config["configurable"]["thread_id"]
            
            thread = await Threads.get(thread_id, user_id=user_id)
            
            if not thread:
                return []

            # Parse thread metadata and config
            thread_metadata = thread.get("metadata", {}) or {}
            
            # FISHY: should we use the assistant metadata or thread metadata to create the graph ??
            # Feature: assistant management. This has to be revisisted on assistant management feature.
            thread_config = thread.get("config") or {}
            thread_config = {
                **thread_config,
                "configurable": {
                    **thread_config.get("configurable", {}),
                    **config.get("configurable", {}),
                },
            }
            assistant_id = thread_metadata.get("assistant_id")
            graph_id = assistant_id # later we will pass the signature. <assistant_id:graph_id>
            
            if graph_id:
                graph = await get_graph(
                        graph_id,
                        thread_config,
                        checkpointer=get_checkpointer(),
                        store=get_store(),
                    )
                
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
            thread_id: UUID,
            seen_runs: set[UUID],
        ) -> list[tuple[UUID, asyncio.Queue]]:
            """Subscribe to the thread stream, creating queues for unseen runs."""
            from langgraph_runtime_inmem.database import connect
            from ...stream_manager import get_stream_manager
            
            stream_manager = get_stream_manager()
            queues = []

            # Create new queues only for runs not yet seen
            thread_id = _ensure_uuid(thread_id)

            # Add thread stream queue
            if thread_id not in seen_runs:
                queue = await stream_manager.add_thread_stream(thread_id)
                queues.append((thread_id, queue))
                seen_runs.add(thread_id)

            async with connect() as conn_:
                for run in conn_.store["runs"]:
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

            from langgraph_runtime_inmem.database import connect
            from ...stream_manager import get_stream_manager
            
            stream_manager = get_stream_manager()
            seen_runs: set[UUID] = set()
            created_queues: list[tuple[UUID, asyncio.Queue]] = []

            try:
                async with connect() as conn_:
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
                            thread_id, seen_runs
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
            from ...stream_manager import get_stream_manager, Message

            topic = f"thread:{thread_id}:stream".encode()

            stream_manager = get_stream_manager()
            payload = STREAM_CODEC.encode(event, message)
            await stream_manager.put_thread(
                str(thread_id), Message(topic=topic, data=payload)
            )

    @staticmethod
    async def count(
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
