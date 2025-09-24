"""
Convert LangGraph-like StateSnapshot (NamedTuple) -> ThreadState (TypedDict).
Defensive, recursive, and JSON-serializable where possible.
"""

from typing import Any, Dict, List, Optional, Sequence
import uuid
import dataclasses
import logging
import json
from langchain_core.messages import BaseMessage

logger = logging.getLogger(__name__)

# --- Utilities / helpers ---

def _is_mapping(obj: Any) -> bool:
    try:
        return hasattr(obj, "items")
    except Exception:
        return False

def _to_primitive(value: Any) -> Any:
    """
    Convert many runtime types into JSON-friendly primitives.
    - dict/list/tuple recursively processed
    - NamedTuple or objects with _asdict -> dict
    - dataclasses -> asdict
    - primitive types returned as-is
    - uuid -> str
    - objects with .content (HumanMessage/AIMessage) -> structured dict
    - fallback to str()
    """
    if value is None:
        return None
    if isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, uuid.UUID):
        return str(value)
    if isinstance(value, dict):
        return {k: _to_primitive(v) for k, v in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_to_primitive(v) for v in value]
    # NamedTuple or similar with _asdict()
    if hasattr(value, "_asdict"):
        try:
            return {k: _to_primitive(v) for k, v in value._asdict().items()}
        except Exception:
            pass
    # dataclass
    if dataclasses.is_dataclass(value):
        return _to_primitive(dataclasses.asdict(value))
    
    # Common message-like objects (langchain style)
    # Attempt to detect HumanMessage / AIMessage like objects
    if isinstance(value, BaseMessage):
        return value.model_dump(exclude_none=True)
    
    # Generic object: try __dict__
    if hasattr(value, "__dict__"):
        try:
            return {k: _to_primitive(v) for k, v in vars(value).items()}
        except Exception:
            pass
    # Fallback to string representation
    try:
        return str(value)
    except Exception:
        return repr(value)


def _extract_checkpoint_from_config(config: Any) -> Optional[Dict[str, Any]]:
    """
    Try to extract Checkpoint-compatible dict from a RunnableConfig-like structure.

    Priority:
    - If config is dict and contains 'configurable' dict, use that
    - If config object has attribute 'configurable', use that
    - Fall back to finding keys thread_id / checkpoint_ns / checkpoint_id / checkpoint_map
    - If nothing found, return None
    """
    if not config:
        return None

    candidate = None
    # dict-like
    if isinstance(config, dict):
        candidate = config.get("configurable") or config.get("checkpoint_map") or config
    else:
        # object-like
        candidate = getattr(config, "configurable", None) or getattr(config, "checkpoint_map", None) or config

    # If candidate is mapping, attempt to pull fields
    if _is_mapping(candidate):
        # normalize keys with safe defaults
        thread_id = candidate.get("thread_id") or candidate.get("thread") or candidate.get("threadId")
        checkpoint_ns = candidate.get("checkpoint_ns") or candidate.get("checkpointNs") or candidate.get("checkpoint_namespace", "")
        checkpoint_id = candidate.get("checkpoint_id") or candidate.get("checkpointId") or candidate.get("checkpoint_id")
        checkpoint_map = candidate.get("checkpoint_map") or candidate.get("checkpointMap") or candidate.get("checkpoint_map")

        # If thread_id is absent but config itself has thread_id keys, check top-level
        if not thread_id and isinstance(config, dict):
            thread_id = config.get("thread_id") or config.get("thread")
            checkpoint_ns = checkpoint_ns or config.get("checkpoint_ns") or config.get("checkpointNs", "")
            checkpoint_id = checkpoint_id or config.get("checkpoint_id")

        # If at least one identifying value exists, return a checkpoint-like dict
        if thread_id or checkpoint_id or checkpoint_ns or checkpoint_map:
            return {
                "thread_id": thread_id or "",
                "checkpoint_ns": checkpoint_ns or "",
                "checkpoint_id": checkpoint_id,
                "checkpoint_map": _to_primitive(checkpoint_map) if checkpoint_map is not None else None,
            }

    # No checkpoint-like structure found
    return None


# --- Main conversion functions ---

def pregel_task_to_thread_task(p: Any) -> Dict[str, Any]:
    """
    Convert a PregelTask object -> ThreadTask dict.
    p is expected to have attributes: id, name, error, interrupts, state, result
    """
    ttask: Dict[str, Any] = {
        "id": getattr(p, "id", None),
        "name": getattr(p, "name", None),
        "error": None,
        "interrupts": [],
        "checkpoint": None,
        "state": None,
        "result": None,
    }

    # error -> string (or None)
    err = getattr(p, "error", None)
    if err is not None:
        try:
            ttask["error"] = str(err)
        except Exception:
            ttask["error"] = repr(err)

    # interrupts -> list (try to keep structure, else primitives)
    interrupts = getattr(p, "interrupts", None) or ()
    try:
        ttask["interrupts"] = [_to_primitive(i) for i in interrupts]
    except Exception:
        ttask["interrupts"] = [str(i) for i in interrupts]

    # result -> dict or wrapped
    res = getattr(p, "result", None)
    if res is not None:
        if isinstance(res, dict):
            ttask["result"] = _to_primitive(res)
        else:
            # wrap non-dict results to preserve content
            ttask["result"] = {"_raw_result": _to_primitive(res)}

    # handle state and checkpoint
    pstate = getattr(p, "state", None)
    # If the PregelTask.state looks like a StateSnapshot (has 'values' and 'config')
    if pstate is not None and hasattr(pstate, "values") and hasattr(pstate, "config"):
        # recursively convert into a ThreadState for the nested state
        try:
            ttask["state"] = state_snapshot_to_thread_state(pstate)
        except Exception as exc:
            logger.exception("Failed to convert nested PregelTask.state to ThreadState: %s", exc)
            ttask["state"] = None
        # try to extract a checkpoint from that nested state's config
        ttask["checkpoint"] = _extract_checkpoint_from_config(getattr(pstate, "config", None))
    else:
        # If pstate is a RunnableConfig-like, try to extract checkpoint info from it
        cp = _extract_checkpoint_from_config(pstate)
        ttask["checkpoint"] = cp

    return ttask


def state_snapshot_to_thread_state(snapshot: Any) -> Dict[str, Any]:
    """
    Convert a StateSnapshot-like object into a ThreadState-like dict.
    snapshot expected to have: values, next, config, metadata, created_at, parent_config, tasks, interrupts
    """
    # Values: preserve mapping or list, ensuring all inner objects are primitive-ready
    raw_values = getattr(snapshot, "values", None)
    if isinstance(raw_values, dict):
        values = {k: _to_primitive(v) for k, v in raw_values.items()}
    elif isinstance(raw_values, (list, tuple)):
        values = [_to_primitive(v) for v in raw_values]
    else:
        # single value - convert
        values = _to_primitive(raw_values)

    # next
    nxt = getattr(snapshot, "next", ())
    try:
        next_nodes: Sequence[str] = list(nxt) if nxt is not None else []
    except Exception:
        # fallback
        next_nodes = [str(nxt)] if nxt is not None else []

    # checkpoint extracted from snapshot.config
    checkpoint = _extract_checkpoint_from_config(getattr(snapshot, "config", None))

    # metadata
    metadata = _to_primitive(getattr(snapshot, "metadata", None))

    # created_at
    created_at = getattr(snapshot, "created_at", None)

    # parent_checkpoint from parent_config
    parent_checkpoint = _extract_checkpoint_from_config(getattr(snapshot, "parent_config", None))

    # tasks: convert all PregelTask -> ThreadTask
    raw_tasks = getattr(snapshot, "tasks", ()) or ()
    tasks_list: List[Dict[str, Any]] = []
    for t in raw_tasks:
        try:
            tasks_list.append(pregel_task_to_thread_task(t))
        except Exception as exc:
            logger.exception("Failed converting a PregelTask: %s", exc)
            tasks_list.append({
                "id": getattr(t, "id", None),
                "name": getattr(t, "name", None),
                "error": "conversion_failure",
                "interrupts": [],
                "checkpoint": None,
                "state": None,
                "result": None
            })

    # interrupts: convert to primitives
    raw_interrupts = getattr(snapshot, "interrupts", ()) or ()
    try:
        interrupts_list = [_to_primitive(i) for i in raw_interrupts]
    except Exception:
        interrupts_list = [str(i) for i in raw_interrupts]

    thread_state = {
        "values": values,
        "next": next_nodes,
        "checkpoint": checkpoint or {
            "thread_id": "",
            "checkpoint_ns": "",
            "checkpoint_id": None,
            "checkpoint_map": None
        },
        "metadata": metadata,
        "created_at": created_at,
        "parent_checkpoint": parent_checkpoint,
        "tasks": tasks_list,
        "interrupts": interrupts_list,
    }

    return thread_state
