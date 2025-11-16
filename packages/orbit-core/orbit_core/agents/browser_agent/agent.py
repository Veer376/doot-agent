from typing import Literal, TypedDict, Annotated
from dataclasses import dataclass
from langchain_core.messages import (
    SystemMessage,
    AIMessage,
    ToolMessage,
    HumanMessage,
    BaseMessage,
)
from langgraph.graph import START, END, StateGraph
from langgraph.runtime import Runtime
from langgraph.prebuilt import ToolNode, tools_condition
from langgraph.graph.message import add_messages
from langchain_google_genai import ChatGoogleGenerativeAI

# Dependency imports
from orbit_core.agents.browser_agent.toolkit.registry import tool_registry
from orbit_core.agents.browser_agent.utils import escalate_error
from orbit_core.utils.logging_utils import get_agent_logger
from orbit_core.agents.browser_agent.message_builder import MessageBuilder
from orbit_core.agents.browser_agent.perception import Screenshot
from orbit_core.agents.llms import LLM, GeminiConfig
from orbit_core.agents.browser_agent.state import AgentState, AgentContext, Snippet, BrowserSnapshot
from orbit_core.agents.browser_agent.browser_runtime import get_browser_context
from orbit_core.clients.checkpointer import get_checkpointer
from orbit_core.agents.llms import LLM, GeminiConfig

logger = get_agent_logger()


async def browser_state_updater(
    agent_state: AgentState, runtime: Runtime[AgentContext]
):
    """Refresh the browser state stored on the agent state."""

    context = runtime.context

    browser_context = await get_browser_context(context)

    if browser_context is None:
        return {}

    try:
        state = await browser_context.get_state(cache_clickable_elements_hashes=True)
    except Exception as exc:
        logger.error("Failed to fetch browser state: %s", exc, exc_info=True)
        return {}

    representation = Screenshot()
    state_content = representation.get_state_content(state, agent_state)

    browser_snapshot: BrowserSnapshot = {
        "url": "loading_url", # FIXME: state_content.get("url"),
        "screenshot": state_content.get("image", ""),
        "dom_text": state_content.get("text", ""),
    }

    return {"browser_snapshot": browser_snapshot}


async def browser_executor(agent_state: AgentState, runtime: Runtime[AgentContext]):
    """Supervisor node which gathers context and calls the LLM."""

    contents = await MessageBuilder().get_context(agent_state)
    tools = tool_registry.get_active_tools(agent_state)

    response = await ChatGoogleGenerativeAI(**GeminiConfig(model="gemini-2.5-flash").__dict__).bind_tools(tools).ainvoke(contents)

    return {
        "messages": [response], 
        "step": agent_state.get('step', 0) + 1
    }


tool_node = ToolNode(tools=list(tool_registry.tools.values()), handle_tool_errors=True)


async def task_summarizer(agent_state: AgentState):
    """Summarizes the task and prepares the final message for the user."""

    system_message = SystemMessage(
        content="""
            You are a task summarizer. Your job is to summarize the task and prepare the final detailed report for the user in first person.
            You may be provided with some last messages, reason of task finish and extracted data.
            Provide the user with the descriptive summary of the task and extracted data in a clean format (if any).
        """
    )
    content = [
        {"type": "text", "text": f"Last messages: {agent_state.get('messages', [])[-3:]}"},
    ]

    response = await LLM(GeminiConfig(model="gemini-2.5-flash")).ainvoke([system_message, HumanMessage(content=content)])

    return {"messages": [response]}


graph = (
    StateGraph(AgentState, AgentContext)
    .add_node("browser_state_updater", browser_state_updater)
    .add_node("browser_executor", browser_executor)
    .add_node("tools", tool_node)
    .add_node("task_summarizer", task_summarizer)
    
    .add_edge(START, "browser_state_updater")
    .add_edge("browser_state_updater", "browser_executor")
    .add_conditional_edges(
        "browser_executor",
        tools_condition,
        {"tools": "tools", "__end__": "task_summarizer"},
    )
    .add_edge("tools", "browser_state_updater")
    .add_edge("task_summarizer", END)
    .compile(checkpointer=get_checkpointer())
)
