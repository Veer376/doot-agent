from __future__ import annotations

import hashlib
import json
from pathlib import Path

from langchain_mcp_adapters.client import MultiServerMCPClient


def conversation_id(thread_id: str, workspace: str | None) -> str:
    normalized = str(Path(workspace).expanduser().resolve()) if workspace else "projectless"
    scope = hashlib.sha256(normalized.encode()).hexdigest()[:16]
    return f"doot:{thread_id}:{scope}"


def result_data(result) -> dict:
    if result.isError:
        raise ValueError("; ".join(getattr(block, "text", "") for block in result.content))
    if result.structuredContent:
        return result.structuredContent
    for block in result.content:
        text = getattr(block, "text", "")
        if "```json" in text:
            return json.loads(text.split("```json", 1)[1].split("```", 1)[0])
    raise ValueError("Local System returned no workspace data")


async def call_local_system(name: str, args: dict, identity: str):
    from .mcp_tools import _connection

    connection = _connection()
    connection["headers"] = {**connection.get("headers", {}), "x-conversation-id": identity}
    client = MultiServerMCPClient({"local_system": connection})
    async with client.session("local_system") as session:
        return await session.call_tool(name, args)


async def workspace_catalog() -> dict:
    return result_data(await call_local_system("workspace", {"action": "list"}, "doot:workspace-catalog"))


def validate_workspace(path: str, roots: list[str]) -> str:
    selected = Path(path).expanduser().resolve(strict=True)
    if not selected.is_dir():
        raise ValueError("Workspace must be a directory")
    for root in roots:
        authorized = Path(root).expanduser().resolve()
        if authorized.exists() and any(parent.samefile(authorized) for parent in (selected, *selected.parents)):
            return str(selected)
    raise ValueError("Workspace is outside the authorized project roots")


async def prepare_workspace(thread_id: str, workspace: str | None) -> str | None:
    if workspace:
        catalog = await workspace_catalog()
        workspace = validate_workspace(workspace, catalog.get("authorizedProjectRoots", []))
    identity = conversation_id(thread_id, workspace)
    result_data(await call_local_system("bridge_context", {}, identity))
    if workspace:
        result_data(await call_local_system("workspace", {"action": "open", "path": workspace}, identity))
    return workspace
