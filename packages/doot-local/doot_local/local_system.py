"""Allowlisted Local System MCP tools, scoped to each Doot thread."""
from __future__ import annotations

import asyncio
import json
import os
import re
from pathlib import Path
from urllib.parse import urlparse

from dotenv import dotenv_values
from langchain.tools import ToolRuntime
from langchain_core.messages import ToolMessage
from langchain_core.tools import tool
from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client

from .tools import _resolve_workspace_path, request_user_input
from .workspaces import selected_workspace

MCP_TOOLS = {"execute_command", "apply_patch", "workspace", "manage_task", "write_todos", "view_image"}


def connection_settings():
    url = os.getenv("DOOT_LOCAL_SYSTEM_URL", "http://127.0.0.1:8765/mcp")
    parsed = urlparse(url)
    if parsed.scheme != "http" or parsed.hostname not in {"127.0.0.1", "localhost", "::1"}:
        raise ValueError("Local System must use a localhost HTTP endpoint")
    token = os.getenv("DOOT_LOCAL_SYSTEM_TOKEN")
    if not token:
        env_path = Path(os.getenv("DOOT_LOCAL_SYSTEM_ENV_FILE", str(Path.home() / "Projects/chatgpt-local-system/.env")))
        token = dotenv_values(env_path).get("MCP_TOKEN")
    return url, ({"Authorization": f"Bearer {token}"} if token else {})


def effective_arguments(name, args, runtime):
    args = dict(args)
    if name in {"execute_command", "apply_patch"}:
        args["cwd"] = str(_resolve_workspace_path(args.get("cwd") or ".", runtime))
        if name == "apply_patch":
            text = args.get("input", "")
            for line in text.splitlines():
                match = re.match(r"\*\*\* (?:Add File|Update File|Delete File|Move to): (.+)$", line)
                if match:
                    _resolve_workspace_path(str(Path(args["cwd"]) / match.group(1)), runtime)
                elif not text.startswith("*** Begin Patch") and line.startswith(("--- ", "+++ ")):
                    path = line[4:].split("\t", 1)[0]
                    if path != "/dev/null":
                        path = path[2:] if path.startswith(("a/", "b/")) else path
                        _resolve_workspace_path(str(Path(args["cwd"]) / path), runtime)
    elif name == "view_image":
        args["paths"] = [str(_resolve_workspace_path(path, runtime)) for path in args.get("paths", [])]
    elif name == "workspace" and args.get("action") == "open":
        root = selected_workspace(runtime.context or {})
        requested = _resolve_workspace_path(args.get("path") or str(root), runtime)
        if requested != root:
            raise ValueError("Select a different workspace in Doot before opening it in Local System")
        args["path"] = str(root)
    return args


async def invoke_mcp(name, args, runtime):
    execution = runtime.execution_info
    if not execution or not execution.thread_id:
        raise ValueError("Local System requires a Doot thread")
    url, headers = await asyncio.to_thread(connection_settings)
    headers["x-conversation-id"] = f"doot:{execution.thread_id}"
    arguments = await asyncio.to_thread(effective_arguments, name, args, runtime)
    root = await asyncio.to_thread(selected_workspace, runtime.context or {})
    async with streamablehttp_client(url, headers=headers) as (read, write, _):
        async with ClientSession(read, write) as session:
            await session.initialize()
            # Establish the bridge's per-conversation workspace. Explicit cwd is
            # also sent on filesystem/command calls, so ambient selection cannot
            # redirect them. MCP tasks and todos use the same stable thread ID.
            if name != "workspace":
                opened = await session.call_tool("workspace", {"action": "open", "path": str(root)})
                if opened.isError:
                    raise RuntimeError("Local System rejected the selected workspace: " + " ".join(getattr(c, "text", "") for c in opened.content))
            result = await session.call_tool(name, arguments)
    return result_message(name, result, runtime.tool_call_id)


def result_message(name, result, tool_call_id):
    data = result.structuredContent
    if data is None:
        for block in result.content:
            match = re.search(r"```json\s*(.*?)\s*```", getattr(block, "text", ""), re.S)
            if match:
                try:
                    data = json.loads(match.group(1))
                except json.JSONDecodeError:
                    pass
                break
    payload = {"content": [c.model_dump(mode="json") for c in result.content if c.type == "text"],
               "structuredContent": data, "isError": bool(result.isError)}
    content = json.dumps(payload)
    if any(block.type == "image" for block in result.content):
        content = []
        for block in result.content:
            if block.type == "text":
                content.append({"type": "text", "text": block.text})
            elif block.type == "image":
                content.append({"type": "image_url", "image_url": {"url": f"data:{block.mimeType};base64,{block.data}"}})
        if data is not None:
            content.append({"type": "text", "text": json.dumps(data)})
    return ToolMessage(content=content, name=name, tool_call_id=tool_call_id,
                       status="error" if result.isError else "success")


def bridge_tool(definition):
    name = definition.name

    @tool(name, description=definition.description or name, args_schema=definition.inputSchema)
    async def call(runtime: ToolRuntime, **kwargs):
        return await invoke_mcp(name, kwargs, runtime)

    return call


async def load_tools():
    url, headers = await asyncio.to_thread(connection_settings)
    async with streamablehttp_client(url, headers=headers) as (read, write, _):
        async with ClientSession(read, write) as session:
            await session.initialize()
            definitions = (await session.list_tools()).tools
    found = {definition.name: definition for definition in definitions if definition.name in MCP_TOOLS}
    if MCP_TOOLS - found.keys():
        raise RuntimeError("Local System is missing tools: " + ", ".join(sorted(MCP_TOOLS - found.keys())))
    # Human input stays native to Doot's interrupt UI rather than opening the
    # bridge's separate questionnaire UI. It is still a native agent tool.
    return await asyncio.to_thread(lambda: [bridge_tool(found[name]) for name in sorted(found)] + [request_user_input])
