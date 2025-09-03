from typing import Literal
from langchain_core.messages import (
    SystemMessage,
    AIMessage,
    ToolMessage,
    HumanMessage,
)
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import START, END, StateGraph
from langgraph.types import Command
from langgraph.runtime import Runtime

# Dependency imports
from .toolkit.registry import tool_registry
from .utils import escalate_error
from logging_utils import get_agent_logger
from .message_builder import MessageBuilder
from .perception import BrowserRepresentationType
from ..llm import LLM, GeminiLLM, LangChainLLM, LLMConfig
from .toolkit import ToolResult
from .messages.error_messages import ToolCallMissing, InvalidToolCall
from .types import AgentState, AgentContext, MessageBlueprint

logger = get_agent_logger()


async def _browser_executor(agent_state: AgentState, runtime: Runtime[AgentContext]):
    """Supervisor node which gathers context and calls the LLM."""
    
    context = runtime.context
    
    msg_blueprint: MessageBlueprint = await MessageBuilder().build_message_blueprint(
        context, agent_state
    )

    llm: LLM = LangChainLLM() if context.llm == "langchain" else GeminiLLM()

    response = await llm(msg_blueprint, context.llm_config)

    return {
        "messages": [response], 
        "step": agent_state.step + 1
    }


@escalate_error
async def _tool_executor(agent_state: AgentState, runtime: Runtime[AgentContext]):
    """Custom tool node that handles tool execution."""

    logger = get_agent_logger("tool_executor")
    
    context: AgentContext = runtime.context
    
    tool_calls = (
        getattr(agent_state.messages[-1], "tool_calls", [])
        if len(agent_state.messages) > 0
        else []
    )

    if not tool_calls:
        logger.warning("No tool calls found", context.browser_context)
        raise ToolCallMissing()

    tool_results = []
    reserved_tools = []

    # FIXME: Check if the browser state has been changed since the last action.
    for tool_call in tool_calls:
        tool_name = tool_call["name"]

        tool = tool_registry.tools.get(tool_name)

        logger.debug(
            f"Executing tool: {tool_name} with args: {tool_call['args']}",
            context.browser_context,
        )

        try:
            result: ToolResult | Command = await tool(
                **tool_call["args"], browser_context=context.browser_context
            )

        except ValueError as e:
            logger.error(
                f"Error occurred while calling tool '{tool_name}': {e}",
                context.browser_context,
            )
            raise InvalidToolCall()

        if isinstance(result, Command):
            continue

        if result.status == "error":
            agent_state.consecutive_failures.append(result.message)
        else:
            agent_state.consecutive_failures.clear()

        reserved_tools.extend(getattr(result, "reserve_tools", []) or [])

        tool_results.append(
            ToolMessage(
                tool_call_id=tool_call.get("id"),
                name=tool_name,
                status=result.status,
                content=(
                    [result.message, result.data] if result.data else [result.message]
                ),
                artifact=result.to_dict(),
            )
        )

    return {
        "messages": tool_results,
        "last_actions": [tool_result.name for tool_result in tool_results],
        "reserved_tools": reserved_tools,
    }


async def _task_summarizer(state: AgentState):
    """Summarizes the task and prepares the final message for the user."""

    system_message = SystemMessage(
        content="""
            You are a task summarizer. Your job is to summarize the task and prepare the final detailed report for the user in first person.
            You may be provided with some last messages, reason of task finish and extracted data.
            Provide the user with the descriptive summary of the task and extracted data in a clean format (if any).
        """
    )

    content = [
        {"type": "text", "text": f"Last messages: {state.messages[-3:]}"},
        {"type": "text", "text": f"Task: {state.task}"},
    ]
    
    llm = LangChainLLM()
    response = await llm([system_message, HumanMessage(content=content)])

    return {"messages": [response]}


def _route_condition(state: AgentState) -> Literal["continue", "conclude", "end"]:
    logger = get_agent_logger("router")

    messages = state.messages
    last_message = messages[-1] if messages else None

    if (
        isinstance(last_message, AIMessage)
        and hasattr(last_message, "tool_calls")
        and last_message.tool_calls
    ):
        tool_call = last_message.tool_calls[0]

        if tool_call.get("name") == "finish_task":
            # Log without browser context to avoid asyncio issues during shutdown
            logger.debug("Finish task tool called, ending task.")
            return "conclude"

    return "continue"

graph = (
    StateGraph(AgentState, context_schema=AgentContext)
    .add_node("browser_executor", _browser_executor)
    .add_node("tool_executor", _tool_executor)
    .add_node("task_summarizer", _task_summarizer)
    .add_edge(START, "browser_executor")
    .add_conditional_edges(
        "browser_executor",
        _route_condition,
        {"continue": "tool_executor", "end": END, "conclude": "task_summarizer"},
    )
    .add_edge("tool_executor", "browser_executor")
    .add_edge("task_summarizer", END)
    .compile()
)