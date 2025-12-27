from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Sequence, Union, Literal, TypedDict
from uuid import UUID
from pydantic import BaseModel, Field, HttpUrl
from langgraph_sdk.schema import (
    ThreadSelectField,
    ThreadSortBy,
    ThreadStatus,
    SortOrder,
    Command,
    Config,
    Context,
    Durability,
    IfNotExists,
    MultitaskStrategy,
    DisconnectMode,
    StreamMode,
    RunStatus,
    AssistantSelectField,
    AssistantSortBy,
)

Json = Dict[str, Any] | None
IfExists = Literal["raise", "do_nothing"]


class TTL(TypedDict):
    strategy: str
    ttl: int


class ThreadSuperstepUpdate(TypedDict):
    as_node: str
    command: Command | None
    values: dict[str, Any] | None


@dataclass
class ThreadCreate:
    """Payload for creating a thread."""

    if_exists: IfExists = "raise"
    metadata: dict[str, Any] | None = None
    supersteps: list[Any] | None = None
    thread_id: str | None = None
    ttl: TTL | None = None

    def __getitem__(self, key):
        return getattr(self, key)

    def get(self, key, default=None):
        return getattr(self, key, default)


@dataclass
class ThreadPatch:
    """Payload for updating a thread."""

    metadata: dict[str, Any] | None = None
    ttl: TTL | None = None

    def __getitem__(self, key):
        return getattr(self, key)

    def get(self, key, default=None):
        return getattr(self, key, default)


@dataclass
class ThreadSearchRequest:
    """Payload for listing threads."""

    ids: Sequence[str] | None = None
    limit: int = 10
    metadata: Json = None
    offset: int = 0
    select: list[ThreadSelectField] | None = None
    sort_by: ThreadSortBy = "updated_at"
    sort_order: SortOrder = "desc"
    status: ThreadStatus | None = None
    values: Json = None

    def __getitem__(self, key):
        return getattr(self, key)

    def get(self, key, default=None):
        return getattr(self, key, default)


class Checkpoint(TypedDict, total=False):
    thread_id: str
    checkpoint_ns: (
        str  # Namespace for the checkpoint; used internally to manage subgraph state.
    )
    checkpoint_id: str | None
    checkpoint_map: dict[str, Any] | None


class RunCreateStateful(TypedDict, total=False):
    """Payload for creating a run."""

    assistant_id: str
    after_seconds: int | None
    checkpoint: Checkpoint | None
    checkpoint_during: bool
    command: dict[str, Any] | None
    config: dict[str, Any] | None
    context: dict[str, Any] | None
    durability: Literal["async", "ephemeral"]
    feedback_keys: list[str] | None
    if_not_exists: Literal["create", "reject"]
    input: dict[str, Any] | None
    interrupt_before: str | list[str] | None
    interrupt_after: str | list[str] | None
    metadata: Json
    multitask_strategy: Literal["reject", "rollback", "interrupt", "enqueue"]
    on_disconnect: Literal["cancel", "continue"]
    stream_mode: list[str] | str
    stream_resumable: bool
    stream_subgraphs: bool
    webhook: str | None


class ThreadStateSearch(TypedDict, total=False):
    before: Config | None = None
    checkpoint: Checkpoint | None = None
    limit: int = 10
    metadata: Json = None


class Run(TypedDict):
    run_id: str
    thread_id: str
    assistant_id: str
    status: RunStatus
    metadata: dict[str, Any]
    multitask_strategy: MultitaskStrategy
    created_at: str
    updated_at: str
    kwargs: dict[str, Any]


@dataclass
class Assistant:
    assistant_id: str
    config: Config
    created_at: str
    graph_id: str
    metadata: dict[str, Any]
    updated_at: str
    context: Context | None = None
    description: str | None = None
    name: str | None = None
    version: str | None = None
    
    def __getitem__(self, key):
        return getattr(self, key)
    
    def get(self, key, default=None):
        return getattr(self, key, default)
    

class AssistantSearchRequest(TypedDict, total=False):
    """Payload for listing assistants."""

    graph_id: str
    limit: int = 10
    metadata: Json
    offset: int = 0
    select: list[AssistantSelectField]
    sort_by: AssistantSortBy
    sort_order: SortOrder
