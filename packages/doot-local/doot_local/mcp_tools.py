from __future__ import annotations

import asyncio
import os
from concurrent.futures import ThreadPoolExecutor
from functools import lru_cache
from pathlib import Path

from langchain_core.tools import BaseTool
from langchain_mcp_adapters.client import MultiServerMCPClient
from langchain_mcp_adapters.interceptors import MCPToolCallRequest

from .workspaces import conversation_id


async def workspace_interceptor(request: MCPToolCallRequest, handler):
    runtime = request.runtime
    context = getattr(runtime, "context", None) or {}
    execution = getattr(runtime, "execution_info", None)
    config = getattr(runtime, "config", {}) or {}
    thread_id = getattr(execution, "thread_id", None) or config.get("configurable", {}).get("thread_id")
    if not thread_id:
        raise ValueError("A LangGraph thread is required for local tool execution")
    workspace = context.get("workspace")
    args = dict(request.args)
    if workspace and request.name in {"execute_command", "apply_patch"}:
        root = Path(workspace).expanduser().resolve()
        cwd = Path(args.get("cwd") or root).expanduser().resolve()
        if not cwd.is_relative_to(root):
            raise ValueError("Tool working directory is outside the selected workspace")
        args["cwd"] = str(cwd)
    if workspace and request.name == "workspace" and args.get("action") == "open":
        args["path"] = workspace
    return await handler(request.override(
        args=args,
        headers={**(request.headers or {}), "x-conversation-id": conversation_id(str(thread_id), workspace)},
    ))


DEFAULT_LOCAL_SYSTEM_MCP_URL = "http://127.0.0.1:8765/mcp"


def _connection() -> dict:
    url = os.getenv("DOOT_LOCAL_SYSTEM_MCP_URL", DEFAULT_LOCAL_SYSTEM_MCP_URL)
    token = os.getenv("DOOT_LOCAL_SYSTEM_MCP_TOKEN") or os.getenv("MCP_TOKEN")
    connection: dict = {
        "transport": "streamable_http",
        "url": url,
    }
    if token:
        connection["headers"] = {"Authorization": f"Bearer {token}"}
    return connection


async def _load_tools() -> list[BaseTool]:
    client = MultiServerMCPClient({"local_system": _connection()}, tool_interceptors=[workspace_interceptor])
    tools = await client.get_tools()
    if not tools:
        raise RuntimeError("Local System MCP returned no tools")
    return tools


def _run_async(coro_factory):
    """Run MCP discovery during graph construction, even if an event loop exists."""
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro_factory())

    # LangGraph may import graph modules from an async server lifecycle. Run the
    # one-time MCP discovery in a dedicated thread rather than nesting loops.
    with ThreadPoolExecutor(max_workers=1, thread_name_prefix="doot-mcp-loader") as pool:
        return pool.submit(lambda: asyncio.run(coro_factory())).result()


@lru_cache(maxsize=1)
def load_local_system_tools() -> tuple[BaseTool, ...]:
    try:
        return tuple(_run_async(_load_tools))
    except Exception as exc:
        url = _connection()["url"]
        raise RuntimeError(
            f"Unable to load Local System MCP tools from {url}. "
            "Make sure Local System is running before starting the Doot graph."
        ) from exc

