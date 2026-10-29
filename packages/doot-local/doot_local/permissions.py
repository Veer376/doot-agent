from __future__ import annotations

import asyncio
import hashlib
import json
import os
import sqlite3
from pathlib import Path
from typing import NotRequired
from langchain.agents.middleware import AgentState
from contextlib import contextmanager
from types import SimpleNamespace

from langchain.agents.middleware import HumanInTheLoopMiddleware

from .config import load_settings

MODES = {"ask", "auto", "full"}
READ_TOOLS = {"runtime_status", "list_workspace", "view_image"}
WRITE_TOOLS = {"apply_patch"}


def state_directory() -> Path:
    directory = Path(os.environ.get("DOOT_STATE_DIR", str(load_settings().workspace_root / ".langgraph_api" / "doot"))).expanduser().resolve()
    directory.mkdir(parents=True, exist_ok=True)
    return directory


@contextmanager
def connection():
    db = sqlite3.connect(state_directory() / "permissions.sqlite3", timeout=10)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA journal_mode=WAL")
    db.execute("CREATE TABLE IF NOT EXISTS grants (workspace TEXT NOT NULL, scope TEXT NOT NULL, operation TEXT NOT NULL, tool TEXT NOT NULL, description TEXT NOT NULL, PRIMARY KEY(workspace, scope, operation))")
    db.execute("CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT NOT NULL)")
    try:
        with db:
            yield db
    finally:
        db.close()


def default_mode() -> str:
    with connection() as db:
        row = db.execute("SELECT value FROM settings WHERE key='default_mode'").fetchone()
    return row[0] if row else "ask"


def set_default_mode(mode: str):
    if mode not in MODES:
        raise ValueError("Invalid permission mode")
    with connection() as db:
        db.execute("INSERT OR REPLACE INTO settings VALUES ('default_mode', ?)", (mode,))


def workspace_for(context) -> str:
    from .workspaces import selected_workspace
    return str(selected_workspace(context or {}))


def operation(tool: str, args: dict, workspace: str) -> str:
    identity = {"tool": tool}
    if tool in {"exec_command", "execute_command"}:
        identity.update(command=args.get("command", args.get("cmd", "")), cwd=str((Path(workspace) / (args.get("cwd") or args.get("workdir") or ".")).resolve()))
    else:
        identity["args"] = args
    return hashlib.sha256(json.dumps(identity, sort_keys=True).encode()).hexdigest()


def requires_review(request) -> bool:
    tool = request.tool_call["name"]
    args = request.tool_call["args"]
    context = request.runtime.context or {}
    mode = context.get("permission_mode") or default_mode()
    if mode not in MODES:
        raise ValueError("Invalid permission mode")
    if tool == "write_todos" or (tool == "workspace" and args.get("action") == "list") or (tool == "manage_task" and args.get("action") in {"list", "status"}):
        return False
    tool = request.tool_call["name"]
    if mode == "full" or tool in READ_TOOLS:
        return False
    workspace = workspace_for(context)
    execution = request.runtime.execution_info
    thread_id = execution.thread_id if execution else request.runtime.config.get("configurable", {}).get("thread_id")
    key = operation(tool, request.tool_call["args"], workspace)
    with connection() as db:
        grant = db.execute("SELECT 1 FROM grants WHERE workspace=? AND operation=? AND scope IN (?, 'always')", (workspace, key, f"thread:{thread_id}")).fetchone()
    if grant:
        return False
    return not (mode == "auto" and tool in WRITE_TOOLS)


class PermissionState(AgentState):
    execution_workspace: NotRequired[str]
    execution_permission_mode: NotRequired[str]


def action_identity(name: str, args: dict) -> str:
    return hashlib.sha256(json.dumps({"name": name, "args": args}, sort_keys=True).encode()).hexdigest()


class PermissionMiddleware(HumanInTheLoopMiddleware):
    """Extend the public after_model hook; native HITL owns every decision."""
    state_schema = PermissionState

    def __init__(self, tool_names):
        super().__init__(interrupt_on={
            name: {"allowed_decisions": ["respond"]} if name == "request_user_input" else {"allowed_decisions": ["approve", "reject"], "when": requires_review}
            for name in tool_names
        })

    async def aafter_model(self, state, runtime):
        return await asyncio.to_thread(self.after_model, state, runtime)

    def after_model(self, state, runtime):
        from langchain_core.messages import AIMessage, ToolMessage

        context = runtime.context or {}
        if "execution_workspace" in state and state["execution_workspace"] != workspace_for(context):
            raise ValueError("Cannot change workspace while an action is awaiting approval")
        if "execution_permission_mode" in state and state["execution_permission_mode"] != (context.get("permission_mode") or default_mode()):
            raise ValueError("Cannot change permission mode while an action is awaiting approval")
        grants = context.get("approval_grants", [])
        for grant in grants:
            if grant.get("scope") not in {"conversation", "always"}:
                raise ValueError("Invalid approval scope")
        last_ai = next((message for message in reversed(state["messages"]) if isinstance(message, AIMessage)), None)
        calls = list(last_ai.tool_calls) if last_ai else []
        reviewed = {call["id"] for call in calls if call["name"] != "request_user_input" and requires_review(SimpleNamespace(tool_call=call, runtime=runtime))}
        result = super().after_model(state, runtime)
        # A messages result means native HITL consumed and validated the complete
        # human decision batch. Rejected/responded calls have a synthetic result.
        if not grants or not result or not result.get("messages"):
            return result
        already_answered = {message.tool_call_id for message in result["messages"] if isinstance(message, ToolMessage)}
        eligible = {action_identity(call["name"], call["args"]): call for call in calls if call["id"] in reviewed and call["id"] not in already_answered}
        execution = runtime.execution_info
        if not execution or not execution.thread_id:
            raise ValueError("Remembered permission requires a thread")
        workspace = workspace_for(runtime.context)
        pending = []
        for grant in grants:
            call = eligible.get(action_identity(grant["name"], grant["args"]))
            if call is None:
                # A rejected action never gains permission, even with forged scope
                # metadata. Other mismatches fail before any tool is executed.
                if any(action_identity(c["name"], c["args"]) == action_identity(grant["name"], grant["args"]) and c["id"] in already_answered for c in calls):
                    continue
                raise ValueError("Grant does not match a natively approved action")
            pending.append((workspace, f"thread:{execution.thread_id}" if grant["scope"] == "conversation" else "always", operation(call["name"], call["args"], workspace), call["name"], call["args"].get("command", call["args"].get("cmd", "Workspace file edits"))))
        with connection() as db:
            db.executemany("INSERT OR REPLACE INTO grants VALUES (?, ?, ?, ?, ?)", pending)
        return result


def permission_settings() -> dict:
    with connection() as db:
        grants = [dict(row) for row in db.execute("SELECT * FROM grants ORDER BY workspace, tool, scope")]
    return {"default_mode": default_mode(), "grants": grants, "path": str(state_directory() / "permissions.sqlite3")}


def revoke_grant(workspace: str, scope: str, operation_key: str):
    with connection() as db:
        db.execute("DELETE FROM grants WHERE workspace=? AND scope=? AND operation=?", (workspace, scope, operation_key))
