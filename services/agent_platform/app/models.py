"""For model schema pydantic BaseModel is used for data validation but for the inner fields 
TypedDict validation overhead in complex data strucutres."""
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
    Checkpoint, 
    Command,
    Config,
    Context,
    Durability,
    IfNotExists,
    MultitaskStrategy,
    DisconnectMode,
    StreamMode,
)

Json = Dict[str, Any] | None

# Enum definitions
class IfExists(str, Enum):
    RAISE = "raise"
    DO_NOTHING = "do_nothing"

class RunStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    ERROR = "error"
    SUCCESS = "success"
    TIMEOUT = "timeout"
    INTERRUPTED = "interrupted"

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
    
    if_exists: IfExists = IfExists.RAISE
    metadata: dict[str, Any] | None = None
    supersteps: list[Any] | None = None
    thread_id: str | None = None
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
    sort_by: ThreadSortBy | None = None
    sort_order: SortOrder | None = None
    status: ThreadStatus | None = None
    values: Json = None
    
    def __getitem__(self, key):
        return getattr(self, key)
    
    def get(self, key, default=None):
        return getattr(self, key, default)
    
@dataclass
class RunCreateStateful:
    """Payload for creating a run."""
    
    assistant_id: str
    after_seconds: int | None = None
    checkpoint: Checkpoint | None = None
    checkpoint_during: bool = False
    command: Command | None = None
    config: Config | None = None
    context: Context | None = None
    durability: Durability = "async"
    feedback_keys: list[str] | None = None
    if_not_exists: IfNotExists = "reject"
    input: dict[str, Any] | None = None
    interrupt_before: str | list[str] | None = None
    interrupt_after: str | list[str] | None = None
    metadata: Json = None
    multitask_strategy: MultitaskStrategy = "enqueue"
    on_disconnect: DisconnectMode = "cancel"
    stream_mode: list[StreamMode] | StreamMode = "messages"
    stream_resumable: bool = False  
    stream_subgraphs: bool = False
    webhook: str | None = None
    
    def __getitem__(self, key):
        return getattr(self, key)
    
    def get(self, key, default=None):
        return getattr(self, key, default)
    
    
@dataclass   
class ThreadStateSearch:
    before: Config | None = None
    checkpoint: Checkpoint | None = None
    limit: int = 10
    metadata: Json = None
    
    def __getitem__(self, key):
        return getattr(self, key)
    
    def get(self, key, default=None):
        return getattr(self, key, default)
    