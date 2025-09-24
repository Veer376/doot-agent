from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Sequence, Union, Literal, TypedDict
from uuid import UUID
from pydantic import BaseModel, Field, HttpUrl
from langgraph.types import Command
from langgraph_sdk.schema import ThreadSelectField, ThreadSortBy, ThreadStatus, SortOrder

Node = str
Metadata = Dict[str, Any]
Context = Dict[str, Any]
Version = str
Name = str
Description = str | None
Schedule = str
Payload = Dict[str, Any]
StateSchema = Dict[str, Any]
ConfigSchema = Dict[str, Any] | None
ContextSchema = Dict[str, Any] | None
InputSchema = Dict[str, Any]
OutputSchema = Dict[str, Any]
Kwargs = Dict[str, Any]
Checkpoint = str | None
Interrupts = List[Any]
Before = Any
Key = str
Filter = Dict[str, Any]
Json = Dict[str, Any] | None

# Enum definitions
class IfExists(str, Enum):
    RAISE = "raise"
    DO_NOTHING = "do_nothing"


class MultitaskStrategy(str, Enum):
    REJECT = "reject"
    ROLLBACK = "rollback"
    INTERRUPT = "interrupt"
    ENQUEUE = "enqueue"


class SortBy(str, Enum):
    CRON_ID = "cron_id"
    ASSISTANT_ID = "assistant_id"
    THREAD_ID = "thread_id"
    NEXT_RUN_DATE = "next_run_date"
    END_TIME = "end_time"
    CREATED_AT = "created_at"
    UPDATED_AT = "updated_at"


class RunStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    ERROR = "error"
    SUCCESS = "success"
    TIMEOUT = "timeout"
    INTERRUPTED = "interrupted"


class Durability(str, Enum):
    SYNC = "sync"
    ASYNC = "async"
    EXIT = "exit"


class IfNotExists(str, Enum):
    CREATE = "create"
    REJECT = "reject"


class OnCompletion(str, Enum):
    DELETE = "delete"
    KEEP = "keep"


class OnDisconnect(str, Enum):
    CANCEL = "cancel"
    CONTINUE = "continue"


class StreamMode(str, Enum):
    VALUES = "values"
    MESSAGES = "messages"
    MESSAGES_TUPLE = "messages-tuple"
    TASKS = "tasks"
    CHECKPOINTS = "checkpoints"
    UPDATES = "updates"
    EVENTS = "events"
    DEBUG = "debug"
    CUSTOM = "custom"

class RunsCancelStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    ALL = "all"

class TTL(BaseModel):
    strategy: str = Field("delete", description="TTL strategy, e.g., 'delete'")
    ttl: int = Field(..., description="Time-to-live in minutes")

# class Command(BaseModel):
    
    
# class ThreadSuperstepUpdate(BaseModel):
#     as_node: str = Field(..., description="The node to update the superstep for.")
#     command: Command | None = Field(None, description="The command to run.")
#     values: dict[str, Any] | None = Field(None, description="New values to update in the thread state.")    
    
# ThreadCreate model
class ThreadCreate(BaseModel):
    """Payload for creating a thread."""
    
    if_exists: IfExists = Field(
        IfExists.RAISE,
        description="How to handle duplicate creation. Must be either 'raise' (raise error if duplicate), or 'do_nothing' (return existing thread).",
    )
    metadata: dict[str, Any] | None = Field(None, description="Metadata to add to thread.")
    supersteps: list[Any] | None = Field(
        None, description="Initial supersteps to set in the thread."
    )
    thread_id: str | None = Field(None, description="The ID of the thread. If not provided, a random UUID will be generated.",)
    ttl: TTL | None = Field(None, description="Time-to-live for this thread.")


class ThreadSearchRequest(BaseModel):
    
    ids: Sequence[str] | None = Field(None, description="List of thread IDs to search for.")
    limit: int | None = Field(10, description="Maximum number of threads to return.")
    metadata: Json = Field(None, description="Metadata key-value pairs to filter threads.")
    offset: int = Field(0, description="Number of threads to skip for pagination.")
    select: list[ThreadSelectField] | None = Field(None, description="List of fields to include in the response.")
    sort_by: ThreadSortBy | None = Field(None, description="Field to sort the results by.")
    sort_order: SortOrder | None = Field(None, description="Sort order, either 'asc' or 'desc'.")
    status: ThreadStatus | None = Field(None, description="Filter threads by their status.")
    values: Json = Field(None, description="Filter threads by their values.")
    
