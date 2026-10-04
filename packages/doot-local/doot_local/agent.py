from __future__ import annotations

from functools import lru_cache
from typing import TypedDict

from langchain.agents import create_agent
from langchain.agents.middleware import AgentMiddleware, ModelRequest
from langchain_anthropic import ChatAnthropic

from .config import load_settings
from .mcp_tools import load_local_system_tools
from .workspaces import prepare_workspace


SYSTEM_PROMPT = """You are Doot, a local engineering agent.

You run on the user's machine through a local LangGraph server. Your model requests
must go through the configured Antigravity proxy.

Your machine capabilities come from the Local System MCP server. Before the first
machine action in a turn, call bridge_context. Use workspace to select the intended
project before project work. Treat the user's instruction as the goal, verify
important assumptions against current state, and carry reversible in-scope work
through implementation and validation.

Be concise and execution-oriented. Local System can execute commands and modify
files, so inspect before destructive or consequential actions and request user input
when approval or human attention is genuinely required. Never claim that a file,
command, deployment, or external action succeeded unless a tool confirms it.
"""


class AgentContext(TypedDict, total=False):
    model: str
    workspace: str | None


@lru_cache(maxsize=24)
def _model_for_name(model_name: str) -> ChatAnthropic:
    settings = load_settings()
    return ChatAnthropic(
        model=model_name,
        api_key=settings.api_key,
        base_url=settings.proxy_url,
        timeout=settings.timeout_seconds,
        max_retries=settings.max_retries,
        max_tokens=4096,
    )


def _apply_selected_model(request: ModelRequest[AgentContext]):
    context = request.runtime.context or {}
    selected = context.get("model") if isinstance(context, dict) else None
    if selected:
        return request.override(model=_model_for_name(str(selected)))
    return request


class SelectModelMiddleware(AgentMiddleware):
    def wrap_model_call(self, request: ModelRequest[AgentContext], handler):
        return handler(_apply_selected_model(request))

    async def awrap_model_call(self, request: ModelRequest[AgentContext], handler):
        return await handler(_apply_selected_model(request))


class WorkspaceMiddleware(AgentMiddleware):
    async def abefore_agent(self, state, runtime):
        context = runtime.context or {}
        execution = runtime.execution_info
        if not execution or not execution.thread_id:
            raise ValueError("A LangGraph thread is required")
        await prepare_workspace(str(execution.thread_id), context.get("workspace"))

    async def awrap_model_call(self, request, handler):
        from langchain_core.messages import SystemMessage

        context = request.runtime.context or {}
        workspace = context.get("workspace")
        if workspace:
            message = request.system_message
            content = message.content if message else ""
            blocks = [{"type": "text", "text": content}] if isinstance(content, str) else list(content)
            blocks.append({"type": "text", "text": f"Current workspace: {workspace}"})
            request = request.override(system_message=SystemMessage(content=blocks))
        return await handler(request)


def build_graph():
    settings = load_settings()
    model = _model_for_name(settings.model)
    tools = list(load_local_system_tools())

    return create_agent(
        model=model,
        tools=tools,
        middleware=[WorkspaceMiddleware(), SelectModelMiddleware()],
        system_prompt=SYSTEM_PROMPT,
        context_schema=AgentContext,
        name="doot",
    )


graph = build_graph()
