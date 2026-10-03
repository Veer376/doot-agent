from __future__ import annotations

from langchain.agents import create_agent
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


def build_graph():
    settings = load_settings()
    model = ChatAnthropic(
        model=settings.model,
        api_key=settings.api_key,
        base_url=settings.proxy_url,
        timeout=settings.timeout_seconds,
        max_retries=settings.max_retries,
        max_tokens=4096,
    )

    return create_agent(
        model=model,
        tools=TOOLS,
        system_prompt=SYSTEM_PROMPT,
        name="doot",
    )


graph = build_graph()
