from __future__ import annotations

from functools import lru_cache
from typing import TypedDict

from langchain.agents import create_agent
from langchain.agents.middleware import AgentMiddleware, ModelRequest
from langchain_anthropic import ChatAnthropic

from .config import load_settings
from .tools import TOOLS


SYSTEM_PROMPT = """You are Doot, a local engineering agent.

You run on the user's machine through a local LangGraph server. Your model requests
must go through the configured Antigravity proxy.

Be concise and execution-oriented. Use tools when they are relevant. Current local
file tools are restricted to the configured workspace. The command tool executes
locally and is intentionally not sandboxed, so inspect before destructive actions.
Never claim that a file or command changed unless a tool confirms it.
"""


class AgentContext(TypedDict, total=False):
    model: str


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


def build_graph():
    settings = load_settings()
    model = _model_for_name(settings.model)

    return create_agent(
        model=model,
        tools=TOOLS,
        middleware=[SelectModelMiddleware()],
        system_prompt=SYSTEM_PROMPT,
        context_schema=AgentContext,
        name="doot",
    )


graph = build_graph()
