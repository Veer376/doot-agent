from langgraph.types import Command, Send, Interrupt, StateSnapshot
from typing import cast, TYPE_CHECKING, Any
from langgraph.pregel import Pregel
from pydantic import create_model
from pydantic import TypeAdapter
import uuid
from uuid import UUID, uuid4
import base64
import json
import asyncio
from collections import defaultdict
from orbit_core.clients.checkpointer import get_checkpointer

if TYPE_CHECKING:
    from langgraph_sdk.schema import Interrupt as InterruptSchema
    from langchain_core.runnables.config import RunnableConfig
    from langgraph_sdk.schema import Checkpoint, ThreadState

# Only gate features on the major.minor version
from langgraph.version import __version__

LANGGRAPH_PY_MINOR = tuple(map(int, __version__.split(".")[:2]))
USE_NEW_INTERRUPTS = LANGGRAPH_PY_MINOR >= (0, 6)

class ValueEvent(asyncio.Event):
    def set(self, value: Any = True) -> None:
        """Set the internal flag to true. All coroutines waiting for it to
        become set are awakened. Coroutine that call wait() once the flag is
        true will not block at all.
        """
        if not self._value:
            self._value = value

            for fut in self._waiters:
                if not fut.done():
                    fut.set_result(value)

    async def wait(self):
        """Block until the internal flag is set.

        If the internal flag is set on entry, return value
        immediately.  Otherwise, block until another coroutine calls
        set() to set the flag, then return the value.
        """
        if self._value:
            return self._value

        fut = self._get_loop().create_future()
        self._waiters.append(fut)
        try:
            return await fut
        finally:
            self._waiters.remove(fut)


def map_cmd(cmd: dict) -> Command:
    goto = cmd.get("goto")
    if goto is not None and not isinstance(goto, list):
        goto = [cmd.get("goto")]

    update = cmd.get("update")
    if isinstance(update, tuple | list) and all(
        isinstance(t, tuple | list) and len(t) == 2 and isinstance(t[0], str)
        for t in cast(list, update)
    ):
        update = [tuple(t) for t in cast(list, update)]

    return Command(
        update=update,
        goto=(
            [
                it if isinstance(it, str) else Send(it["node"], it["input"])  # type: ignore[non-subscriptable]
                for it in goto
            ]
            if goto
            else None
        ),
        resume=cmd.get("resume"),
    )


def state_jsonschema(graph: Pregel) -> dict | None:
    fields: dict = {}
    for k in graph.stream_channels_list:
        v = graph.channels[k]
        try:
            create_model(k, __root__=(v.UpdateType, None)).model_json_schema()
            fields[k] = (v.UpdateType, None)
        except Exception:
            fields[k] = (Any, None)
    return create_model(graph.get_name("State"), **fields).model_json_schema()


EXCLUDED_CONFIG_SCHEMA = (
    "__pregel_checkpointer",
    "__pregel_store",
    "checkpoint_id",
    "checkpoint_ns",
    "thread_id",
)


def get_configurable_jsonschema(graph: Pregel) -> dict:
    """Get the JSON schema for the configurable part of the graph.

    Important: we only return the `configurable` part of the schema.

    The default get_config_schema method returns the entire schema (RunnableConfig),
    which includes other root keys like "max_concurrency", which we
    do not want to expose.

    Args:
        graph: The graph to get the schema for.

    Returns:
       The JSON schema for the configurable part of the graph.

    Whenever we no longer support langgraph < 0.6, we can remove this method
    in favor of graph.get_context_jsonschema().
    """
    # Otherwise, use the config_schema method.
    # TODO: Remove this when we no longer support langgraph < 0.6
    config_schema = graph.config_schema()  # type: ignore[deprecated]
    model_fields = getattr(config_schema, "model_fields", None) or getattr(
        config_schema, "__fields__", None
    )

    if model_fields is not None and "configurable" in model_fields:
        configurable = TypeAdapter(model_fields["configurable"].annotation)
        json_schema = configurable.json_schema()
        if json_schema:
            for key in EXCLUDED_CONFIG_SCHEMA:
                json_schema["properties"].pop(key, None)
        # The type name of the configurable type is not preserved.
        # We'll add it back to the schema if we can.
        if (
            hasattr(graph, "config_type")
            and graph.config_type is not None
            and hasattr(graph.config_type, "__name__")
        ):
            json_schema["title"] = graph.config_type.__name__
        return json_schema
    # If the schema does not have a configurable field, return an empty schema.
    return {}


# ============================================================================
# UUID and Type Conversion Utilities
# ============================================================================


def ensure_uuid(id_: str | UUID | None) -> UUID:
    """Convert a string or UUID to UUID, generating one if None."""
    if isinstance(id_, str):
        return uuid.UUID(id_)
    if id_ is None:
        return uuid4()
    return id_


def snapshot_defaults():
    """Support older versions of langgraph."""
    # Support older versions of langgraph
    if not hasattr(StateSnapshot, "interrupts"):
        return {}
    return {"interrupts": tuple()}


# ============================================================================
# JSONB and Data Utilities
# ============================================================================


def is_jsonb_contained(superset: dict[str, Any], subset: dict[str, Any]) -> bool:
    """
    Implements Postgres' @> (containment) operator for dictionaries.
    Returns True if superset contains all key/value pairs from subset.
    """
    for key, value in subset.items():
        if key not in superset:
            return False
        if isinstance(value, dict) and isinstance(superset[key], dict):
            if not is_jsonb_contained(superset[key], value):
                return False
        elif superset[key] != value:
            return False
    return True


def bytes_decoder(obj):
    """Custom JSON decoder that converts base64 back to bytes."""
    if "__type__" in obj and obj["__type__"] == "bytes":
        return base64.b64decode(obj["value"].encode("utf-8"))
    return obj


def replace_thread_id(data, new_thread_id, thread_id):
    """Replace thread_id in data structure, handling bytes properly."""

    class BytesEncoder(json.JSONEncoder):
        """Custom JSON encoder that handles bytes by converting them to base64."""

        def default(self, obj):
            if isinstance(obj, bytes | bytearray):
                return {
                    "__type__": "bytes",
                    "value": base64.b64encode(
                        obj.replace(
                            str(thread_id).encode(), str(new_thread_id).encode()
                        )
                    ).decode("utf-8"),
                }

            return super().default(obj)

    try:
        json_str = json.dumps(data, cls=BytesEncoder, indent=2)
    except Exception as e:
        raise ValueError(data) from e
    json_str = json_str.replace(str(thread_id), str(new_thread_id))

    # Decoding back from JSON
    d = json.loads(json_str, object_hook=bytes_decoder)
    return d


# ============================================================================
# Interrupt Handling
# ============================================================================


def patch_interrupt(
    interrupt: Interrupt | dict,
) -> "InterruptSchema":
    """Convert a langgraph interrupt (v0 or v1) to standard interrupt schema.

    In v0.4 and v0.5, interrupt_id is a property on the langgraph.types.Interrupt object,
    so we reconstruct the type in order to access the id, with compatibility for the new
    v0.6 interrupt format as well.
    """
    if USE_NEW_INTERRUPTS:
        interrupt = Interrupt(**interrupt) if isinstance(interrupt, dict) else interrupt

        return {
            "id": interrupt.id,
            "value": interrupt.value,
        }
    else:
        if isinstance(interrupt, dict):
            # interrupt_id is a deprecated property on Interrupt and should not be used for initialization
            # id is the new field we use for identification, also not supported on init for old versions
            interrupt.pop("interrupt_id", None)
            interrupt.pop("id", None)
            interrupt = Interrupt(**interrupt)

        return {
            "id": (
                interrupt.interrupt_id if hasattr(interrupt, "interrupt_id") else None
            ),
            "value": interrupt.value,
            "resumable": interrupt.resumable,
            "ns": interrupt.ns,
            "when": interrupt.when,  # type: ignore[unresolved-attribute]
        }


def runnable_config_to_checkpoint(
    config: "RunnableConfig | None",
) -> "Checkpoint | None":
    """Convert RunnableConfig to Checkpoint format."""
    if (
        not config
        or not config["configurable"]
        or "thread_id" not in config["configurable"]
        or not config["configurable"]["thread_id"]
        or "checkpoint_id" not in config["configurable"]
        or not config["configurable"]["checkpoint_id"]
    ):
        return None

    configurable = config["configurable"]
    checkpoint: "Checkpoint" = {  # type: ignore[typed-dict-item]
        "checkpoint_id": configurable["checkpoint_id"],
        "thread_id": configurable["thread_id"],
    }

    if "checkpoint_ns" in configurable:
        checkpoint["checkpoint_ns"] = configurable["checkpoint_ns"] or ""

    if "checkpoint_map" in configurable:
        checkpoint["checkpoint_map"] = configurable["checkpoint_map"]

    return checkpoint


def state_snapshot_to_thread_state(state: StateSnapshot) -> "ThreadState":
    """Convert StateSnapshot to ThreadState format."""
    return {
        "values": state.values,
        "next": state.next,
        "tasks": [
            {
                "id": t.id,
                "name": t.name,
                "path": t.path,
                "error": t.error,
                "interrupts": [patch_interrupt(i) for i in t.interrupts],
                "checkpoint": (
                    t.state["configurable"]
                    if t.state is not None and not isinstance(t.state, StateSnapshot)
                    else None
                ),
                "state": (
                    state_snapshot_to_thread_state(t.state)
                    if isinstance(t.state, StateSnapshot)
                    else None
                ),
                "result": getattr(t, "result", None),
            }
            for t in state.tasks
        ],
        "metadata": state.metadata,
        "created_at": state.created_at,
        "checkpoint": runnable_config_to_checkpoint(state.config),
        "parent_checkpoint": runnable_config_to_checkpoint(state.parent_config),
        "interrupts": [patch_interrupt(i) for i in getattr(state, "interrupts", [])],
        # below are deprecated
        "checkpoint_id": (
            state.config["configurable"].get("checkpoint_id") if state.config else None
        ),
        "parent_checkpoint_id": (
            state.parent_config["configurable"]["checkpoint_id"]
            if state.parent_config
            else None
        ),
    }


# ============================================================================
# Async Utilities
# ============================================================================


async def listen_for_cancellation(
    queue: asyncio.Queue, run_id: UUID, thread_id: UUID | None, done: "ValueEvent"
):
    """Listen for cancellation messages and set the done event accordingly."""
    from langgraph_api.errors import UserInterrupt, UserRollback
    from langgraph_runtime_inmem.inmem_stream import get_stream_manager

    stream_manager = get_stream_manager()

    if control_key := stream_manager.get_control_key(run_id, thread_id):
        payload = control_key.data
        if payload == b"rollback":
            done.set(UserRollback())
        elif payload == b"interrupt":
            done.set(UserInterrupt())

    while not done.is_set():
        try:
            # This task gets cancelled when Runs.enter exits anyway,
            # so we can have a pretty lengthy timeout here
            message = await asyncio.wait_for(queue.get(), timeout=240)
            payload = message.data
            if payload == b"rollback":
                done.set(UserRollback())
            elif payload == b"interrupt":
                done.set(UserInterrupt())
            elif payload == b"done":
                done.set()
                break
        except TimeoutError:
            break


async def empty_generator():
    """Empty async generator."""
    if False:
        yield


# ============================================================================
# Checkpoint Utilities
# ============================================================================


def delete_checkpoints_for_thread(
    thread_id: str | UUID,
    conn,
    run_id: str | UUID | None = None,
):
    """Delete checkpoints for a thread, optionally filtering by run_id."""
    checkpointer = get_checkpointer()
    thread_id = str(thread_id)
    if thread_id not in checkpointer.storage:
        return
    if run_id:
        # Look through metadata
        run_id = str(run_id)
        for checkpoint_ns, checkpoints in list(checkpointer.storage[thread_id].items()):
            for checkpoint_id, (_, metadata_b, _) in list(checkpoints.items()):
                metadata = checkpointer.serde.loads_typed(metadata_b)
                if metadata.get("run_id") == run_id:
                    del checkpointer.storage[thread_id][checkpoint_ns][checkpoint_id]
                    if not checkpointer.storage[thread_id][checkpoint_ns]:
                        del checkpointer.storage[thread_id][checkpoint_ns]
    else:
        del checkpointer.storage[thread_id]
        # Keys are (thread_id, checkpoint_ns, checkpoint_id)
        checkpointer.writes = defaultdict(
            dict, {k: v for k, v in checkpointer.writes.items() if k[0] != thread_id}
        )
