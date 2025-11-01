"""Assistants service - Business logic for assistant operations."""

from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import UTC, datetime
from uuid import UUID, uuid4

import structlog
from starlette.exceptions import HTTPException

from orbit_core.clients import get_supabase

from ...utils import (
    ensure_uuid as _ensure_uuid,
    empty_generator as _empty_generator,
)

import typing

if typing.TYPE_CHECKING:
    from langgraph_api.schema import (
        Assistant,
        AssistantSelectField,
        Config,
        Context,
        MetadataInput,
        OnConflictBehavior,
    )

logger = structlog.stdlib.get_logger(__name__)


class Assistants:
    @staticmethod
    async def search(
        *,
        user_id: str,
        graph_id: str | None,
        metadata: MetadataInput,
        limit: int,
        offset: int,
        sort_by: str | None = None,
        sort_order: str | None = None,
        select: list[AssistantSelectField] | None = None,
    ) -> tuple[AsyncIterator[Assistant], int]:
        metadata = metadata if metadata is not None else {}

        # Get Supabase client
        supabase_client = await get_supabase()

        # Build query
        select_fields = "*"
        if select:
            select_fields = ",".join(select)

        query = (
            supabase_client.table("assistants")
            .select(select_fields, count="exact")
            .eq("user_id", user_id)
        )

        if graph_id:
            query = query.eq("graph_id", graph_id)

        # TODO: Implement metadata filtering with JSONB queries

        # Apply sorting
        sort_by_field = sort_by.lower() if sort_by else "created_at"
        if sort_by_field in (
            "assistant_id",
            "graph_id",
            "name",
            "created_at",
            "updated_at",
        ):
            sort_order_str = sort_order.upper() if sort_order else "DESC"
            query = query.order(sort_by_field, desc=(sort_order_str == "DESC"))
        else:
            query = query.order("created_at", desc=True)

        # Apply pagination
        if limit:
            query = query.limit(limit)
        if offset:
            query = query.offset(offset)

        # Execute query
        result = await query.execute()
        assistants = result.data or []
        total_count = result.count if hasattr(result, "count") else len(assistants)

        cursor = offset + limit if total_count > offset + limit else None

        async def assistant_iterator() -> AsyncIterator[Assistant]:
            for assistant in assistants:
                yield assistant

        return assistant_iterator(), cursor

    @staticmethod
    async def get(
        assistant_id: UUID | str,
        user_id: str,
    ) -> AsyncIterator[Assistant]:
        """Get an assistant by ID."""
        # Get Supabase client
        supabase_client = await get_supabase()

        result = await (
            supabase_client.table("assistants")
            .select("*")
            .eq("assistant_id", str(assistant_id))
            .eq("user_id", user_id)
            .execute()
        )

        async def _yield_result():
            if result.data:
                yield result.data[0]

        return _yield_result()

    @staticmethod
    async def put(
        assistant_id: UUID | str,
        *,
        user_id: str,
        graph_id: str,
        config: Config,
        context: Context,
        metadata: MetadataInput,
        if_exists: OnConflictBehavior,
        name: str,
        description: str | None = None,
    ) -> AsyncIterator[Assistant]:
        """Insert an assistant."""
        metadata = metadata if metadata is not None else {}

        if config.get("configurable") and context:
            raise HTTPException(
                status_code=400,
                detail="Cannot specify both configurable and context. Prefer setting context alone. Context was introduced in LangGraph 0.6.0 and is the long term planned replacement for configurable.",
            )

        # Keep config and context up to date with one another
        if config.get("configurable"):
            context = config["configurable"]
        elif context:
            config["configurable"] = context

        # Get Supabase client
        supabase_client = await get_supabase()

        # Check if assistant already exists
        existing_result = await (
            supabase_client.table("assistants")
            .select("*")
            .eq("assistant_id", str(assistant_id))
            .eq("user_id", user_id)
            .execute()
        )

        existing_assistant = existing_result.data[0] if existing_result.data else None

        if existing_assistant:
            if if_exists == "raise":
                raise HTTPException(
                    status_code=409, detail=f"Assistant {assistant_id} already exists"
                )
            elif if_exists == "do_nothing":

                async def _yield_existing():
                    yield existing_assistant

                return _yield_existing()

        now = datetime.now(UTC)
        new_assistant: Assistant = {
            "assistant_id": str(assistant_id),
            "graph_id": graph_id,
            "config": config or {},
            "context": context or {},
            "metadata": metadata or {},
            "name": name,
            "created_at": now.isoformat(),
            "updated_at": now.isoformat(),
            "version": 1,
            "description": description,
        }

        # Insert into Supabase
        result = await (
            supabase_client.table("assistants")
            .insert({"user_id": user_id, **new_assistant})
            .execute()
        )

        if error := getattr(result, "error", None):
            raise HTTPException(
                status_code=500,
                detail=f"Internal server error: {error} while creating assistant",
            )

        inserted_assistant = result.data[0] if result.data else new_assistant

        # Also insert version record
        new_version = {
            "assistant_id": str(assistant_id),
            "version": 1,
            "graph_id": graph_id,
            "config": config or {},
            "context": context or {},
            "metadata": metadata or {},
            "created_at": now.isoformat(),
            "name": name,
            "description": description,
        }

        await (
            supabase_client.table("assistant_versions")
            .insert({"user_id": user_id, **new_version})
            .execute()
        )

        async def _yield_new():
            yield inserted_assistant

        return _yield_new()

    @staticmethod
    async def patch(
        assistant_id: UUID,
        *,
        user_id: str,
        config: Config | None = None,
        context: Context | None = None,
        graph_id: str | None = None,
        metadata: MetadataInput | None = None,
        name: str | None = None,
        description: str | None = None,
    ) -> AsyncIterator[Assistant]:
        """Update an assistant.

        Args:
            assistant_id: The assistant ID.
            user_id: The user ID.
            graph_id: The graph ID.
            config: The assistant config.
            context: The assistant's static context.
            metadata: The assistant metadata.
            name: The assistant name.
            description: The assistant description.

        Returns:
            return the updated assistant model.
        """
        metadata = metadata if metadata is not None else {}
        config = config if config is not None else {}

        if config.get("configurable") and context:
            raise HTTPException(
                status_code=400,
                detail="Cannot specify both configurable and context. Prefer setting context alone. Context was introduced in LangGraph 0.6.0 and is the long term planned replacement for configurable.",
            )

        # Keep config and context up to date with one another
        if config.get("configurable"):
            context = config["configurable"]
        elif context:
            config["configurable"] = context

        # Get Supabase client
        supabase_client = await get_supabase()

        # Get existing assistant
        existing_result = await (
            supabase_client.table("assistants")
            .select("*")
            .eq("assistant_id", str(assistant_id))
            .eq("user_id", user_id)
            .execute()
        )

        if not existing_result.data:
            raise HTTPException(
                status_code=404, detail=f"Assistant {assistant_id} not found"
            )

        assistant = existing_result.data[0]

        # Get current max version
        versions_result = await (
            supabase_client.table("assistant_versions")
            .select("version")
            .eq("assistant_id", str(assistant_id))
            .eq("user_id", user_id)
            .order("version", desc=True)
            .limit(1)
            .execute()
        )

        new_version = (
            (versions_result.data[0]["version"] + 1) if versions_result.data else 1
        )
        now = datetime.now(UTC)

        new_version_entry = {
            "assistant_id": str(assistant_id),
            "version": new_version,
            "graph_id": graph_id if graph_id is not None else assistant["graph_id"],
            "config": config if config else assistant["config"],
            "context": context if context is not None else assistant.get("context", {}),
            "metadata": (
                {**assistant["metadata"], **metadata}
                if metadata is not None
                else assistant["metadata"]
            ),
            "created_at": now.isoformat(),
            "name": name if name is not None else assistant["name"],
            "description": (
                description if description is not None else assistant.get("description")
            ),
        }

        # Insert new version
        await (
            supabase_client.table("assistant_versions")
            .insert({"user_id": user_id, **new_version_entry})
            .execute()
        )

        # Update assistants table
        update_payload = {
            "graph_id": new_version_entry["graph_id"],
            "config": new_version_entry["config"],
            "context": new_version_entry["context"],
            "metadata": new_version_entry["metadata"],
            "name": name if name is not None else assistant["name"],
            "description": (
                description if description is not None else assistant.get("description")
            ),
            "updated_at": now.isoformat(),
            "version": new_version,
        }

        result = await (
            supabase_client.table("assistants")
            .update(update_payload)
            .eq("assistant_id", str(assistant_id))
            .eq("user_id", user_id)
            .execute()
        )

        updated_assistant = (
            result.data[0] if result.data else {**assistant, **update_payload}
        )

        async def _yield_updated():
            yield updated_assistant

        return _yield_updated()

    @staticmethod
    async def delete(
        assistant_id: UUID,
        user_id: str,
    ) -> AsyncIterator[UUID]:
        """Delete an assistant by ID."""
        # Get Supabase client
        supabase_client = await get_supabase()

        # Get assistant to verify it exists
        existing_result = await (
            supabase_client.table("assistants")
            .select("*")
            .eq("assistant_id", str(assistant_id))
            .eq("user_id", user_id)
            .execute()
        )

        if not existing_result.data:
            raise HTTPException(
                status_code=404, detail=f"Assistant with ID {assistant_id} not found"
            )

        # Delete assistant (cascade should handle versions)
        await (
            supabase_client.table("assistants")
            .delete()
            .eq("assistant_id", str(assistant_id))
            .eq("user_id", user_id)
            .execute()
        )

        # Delete assistant versions
        await (
            supabase_client.table("assistant_versions")
            .delete()
            .eq("assistant_id", str(assistant_id))
            .eq("user_id", user_id)
            .execute()
        )

        # Delete runs associated with this assistant
        runs_result = await (
            supabase_client.table("runs")
            .select("run_id, thread_id")
            .eq("assistant_id", str(assistant_id))
            .eq("user_id", user_id)
            .execute()
        )

        # Import locally to avoid circular imports
        from .runs import Runs

        for run in runs_result.data or []:
            res = await Runs.delete(
                run["run_id"], thread_id=run["thread_id"], user_id=user_id
            )
            await anext(res)

        async def _yield_deleted():
            yield assistant_id

        return _yield_deleted()

    @staticmethod
    async def set_latest(
        assistant_id: UUID,
        version: int,
        user_id: str,
    ) -> AsyncIterator[Assistant]:
        """Change the version of an assistant."""
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
            raise HTTPException(
                status_code=404, detail=f"Assistant {assistant_id} not found"
            )

        assistant = assistant_result.data[0]

        # Get version data
        version_result = await (
            supabase_client.table("assistant_versions")
            .select("*")
            .eq("assistant_id", str(assistant_id))
            .eq("user_id", user_id)
            .eq("version", version)
            .execute()
        )

        if not version_result.data:
            raise HTTPException(
                status_code=404,
                detail=f"Version {version} not found for assistant {assistant_id}",
            )

        version_data = version_result.data[0]

        # Update assistant
        update_payload = {
            "config": version_data["config"],
            "metadata": version_data["metadata"],
            "version": version_data["version"],
            "updated_at": datetime.now(UTC).isoformat(),
        }

        result = await (
            supabase_client.table("assistants")
            .update(update_payload)
            .eq("assistant_id", str(assistant_id))
            .eq("user_id", user_id)
            .execute()
        )

        updated_assistant = (
            result.data[0] if result.data else {**assistant, **update_payload}
        )

        async def _yield_updated():
            yield updated_assistant

        return _yield_updated()

    @staticmethod
    async def get_versions(
        assistant_id: UUID,
        metadata: MetadataInput,
        limit: int,
        offset: int,
        user_id: str,
    ) -> AsyncIterator[Assistant]:
        """Get all versions of an assistant."""
        # Get Supabase client
        supabase_client = await get_supabase()

        # Get assistant to verify it exists and get name/description
        assistant_result = await (
            supabase_client.table("assistants")
            .select("*")
            .eq("assistant_id", str(assistant_id))
            .eq("user_id", user_id)
            .execute()
        )

        if not assistant_result.data:
            raise HTTPException(
                status_code=404, detail=f"Assistant {assistant_id} not found"
            )

        assistant = assistant_result.data[0]

        # Get versions
        query = (
            supabase_client.table("assistant_versions")
            .select("*")
            .eq("assistant_id", str(assistant_id))
            .eq("user_id", user_id)
        )

        # TODO: Implement metadata filtering with JSONB queries

        query = query.order("version", desc=True)

        if limit:
            query = query.limit(limit)
        if offset:
            query = query.offset(offset)

        result = await query.execute()
        versions = result.data or []

        # Ensure name and description are present
        description = assistant.get("description")
        for v in versions:
            if "name" not in v:
                v["name"] = assistant["name"]
            if "description" not in v:
                v["description"] = description
            else:
                description = v["description"]

        async def _yield_versions():
            for version in versions:
                yield version

        return _yield_versions()

    @staticmethod
    async def count(
        *,
        user_id: str,
        graph_id: str | None = None,
        metadata: MetadataInput = None,
    ) -> int:
        """Get count of assistants."""
        # Get Supabase client
        supabase_client = await get_supabase()

        # Build query
        query = (
            supabase_client.table("assistants")
            .select("*", count="exact")
            .eq("user_id", user_id)
        )

        if graph_id:
            query = query.eq("graph_id", graph_id)

        # TODO: Implement metadata filtering with JSONB queries

        # Execute query
        result = await query.execute()

        return result.count if hasattr(result, "count") else 0
