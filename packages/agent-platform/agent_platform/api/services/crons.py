"""Crons service - Business logic for cron operations."""

from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import datetime
from typing import Literal
from uuid import UUID

from langgraph_sdk import Auth
from langgraph_runtime_inmem.database import InMemConnectionProto

import typing

if typing.TYPE_CHECKING:
    from langgraph_api.schema import (
        Cron,
        CronSelectField,
    )


class Crons:
    @staticmethod
    async def put(
        conn: InMemConnectionProto,
        *,
        payload: dict,
        schedule: str,
        cron_id: UUID | None = None,
        thread_id: UUID | None = None,
        end_time: datetime | None = None,
        ctx: Auth.types.BaseAuthContext | None = None,
    ) -> AsyncIterator[Cron]:
        raise NotImplementedError

    @staticmethod
    async def delete(
        conn: InMemConnectionProto,
        cron_id: UUID,
        ctx: Auth.types.BaseAuthContext | None = None,
    ) -> AsyncIterator[UUID]:
        raise NotImplementedError

    @staticmethod
    async def next(
        conn: InMemConnectionProto,
        ctx: Auth.types.BaseAuthContext | None = None,
    ) -> AsyncIterator[Cron]:
        raise NotImplementedError("The in-mem server does not implement Crons.")
        yield {"payload": None}

    @staticmethod
    async def set_next_run_date(
        conn: InMemConnectionProto,
        cron_id: UUID,
        next_run_date: datetime,
        ctx: Auth.types.BaseAuthContext | None = None,
    ) -> None:
        raise NotImplementedError

    @staticmethod
    async def search(
        conn: InMemConnectionProto,
        *,
        assistant_id: UUID | None,
        thread_id: UUID | None,
        limit: int,
        offset: int,
        select: list[CronSelectField] | None = None,
        ctx: Auth.types.BaseAuthContext | None = None,
        sort_by: str | None = None,
        sort_order: Literal["asc", "desc"] | None = None,
    ) -> tuple[AsyncIterator[Cron], int]:
        raise NotImplementedError

    @staticmethod
    async def count(
        conn: InMemConnectionProto,
        *,
        assistant_id: UUID | None = None,
        thread_id: UUID | None = None,
        ctx: Auth.types.BaseAuthContext | None = None,
    ) -> int:
        """Get count of crons."""
        raise NotImplementedError("The in-mem server does not implement Crons.")
