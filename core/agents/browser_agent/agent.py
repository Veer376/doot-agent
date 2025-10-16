from typing import Literal
from langchain_core.messages import (
    SystemMessage,
    AIMessage,
    ToolMessage,
    HumanMessage,
)
from langgraph.graph import START, END, StateGraph
from langgraph.runtime import Runtime

# Dependency imports
from core.agents.browser_agent.toolkit.registry import tool_registry
from core.agents.browser_agent.utils import escalate_error
from core.utils.logging_utils import get_agent_logger
from core.agents.browser_agent.message_builder import MessageBuilder
from core.agents.browser_agent.perception import Screenshot
from core.agents.llm import LLM, GeminiLLM, LangChainLLM, LLMConfig
from core.agents.browser_agent.toolkit import ToolResult
from core.agents.browser_agent.messages.error_messages import ToolCallMissing, InvalidToolCall
from core.agents.browser_agent.types import AgentState, AgentContext, MessageBlueprint, Snippet, BrowserSnapshot
from core.agents.browser_agent.browser_runtime import get_browser_context
from core.clients.langgraph_checkpointer import checkpointer
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_google_genai._enums import HarmBlockThreshold, HarmCategory

logger = get_agent_logger()

model = ChatGoogleGenerativeAI(
        model="gemini-2.5-flash",
        temperature=1,
        max_retries=2,
        max_output_tokens=None,
        include_thoughts=True,
        thinking_budget=-1,
        # Configure native Gemini tools on model creation
        tools=[
            {"google_search_retrieval": {"dynamic_retrieval_config": {"mode": "MODE_DYNAMIC", "dynamic_threshold": 0.3}}}
        ],
        safety_settings={
            HarmCategory.HARM_CATEGORY_HARASSMENT: HarmBlockThreshold.BLOCK_NONE,
            HarmCategory.HARM_CATEGORY_HATE_SPEECH: HarmBlockThreshold.BLOCK_NONE,
            HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT: HarmBlockThreshold.BLOCK_NONE,
            HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT: HarmBlockThreshold.BLOCK_NONE,
            HarmCategory.HARM_CATEGORY_CIVIC_INTEGRITY: HarmBlockThreshold.BLOCK_NONE,
        }
    )
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
    except Exception as exc:  # noqa: BLE001
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
    
    response = await model.bind_tools(tools).ainvoke(contents)

    return {
        "messages": [response], 
        "step": agent_state.get('step', 0) + 1
    }


@escalate_error
async def tool_executor(agent_state: AgentState, runtime: Runtime[AgentContext]):
    """Custom tool node that handles tool execution."""

    logger = get_agent_logger("tool_executor")

    context: AgentContext = runtime.context
    browser_context = await get_browser_context(context)

    tool_calls = (
        getattr(agent_state.get('messages', [])[-1], "tool_calls", [])
        if len(agent_state.get('messages', [])) > 0
        else []
    )

    if not tool_calls:
        logger.warning("No tool calls found", browser_context)
        raise ToolCallMissing()

    tool_results = []
    reserved_tools = []

    # FIXME: Check if the browser state has been changed since the last action.
    for tool_call in tool_calls:
        tool_name = tool_call["name"]
        tool = tool_registry.tools.get(tool_name)

        if tool is None:
            logger.error("Tool '%s' not found", tool_name)
            raise InvalidToolCall()

        logger.debug(
            f"Executing tool: {tool_name} with args: {tool_call['args']}",
            browser_context,
        )

        try:
            result: ToolResult = await tool(
                **tool_call["args"], browser_context=browser_context
            )

        except ValueError as e:
            logger.error(
                f"Error occurred while calling tool '{tool_name}': {e}",
                browser_context,
            )
            raise InvalidToolCall()

        if isinstance(result, Snippet):
            agent_state.get('scratchpad', []).append(result)
            tool_results.append(
                ToolMessage(
                    tool_call_id=tool_call.get("id"),
                    name=tool_name,
                    content=[],
                    # artifact is used to pass the tool message to the function response of gemini.
                    artifact={
                        "status": "success",
                    },
                )
            )

        if result.status == "error":
            agent_state.get('consecutive_failures', []).append(result.message)
        else:
            agent_state.get('consecutive_failures', []).clear()

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


async def plan_reflect(agent_state: AgentState, runtime: Runtime[AgentContext]):
    """Plans the next action for the agent based on the current state."""

    system_message = SystemMessage(
        content="""
            You are a plan and reflex agent, your job is to reflex on the past actions and plan and guide the AI in the best possible way.
            You will be provided with the task, scratchpad(previous actions), and current browser_state also. You have the respond with the next appropriate action we can take to fulfill the user task.
            If AI actions are aligned and task will be achevied then just summarize the scratchpad in plan text without action tag.
        """
    )
    content = f"""
        Scratchpad: {agent_state.get('scratchpad', [])}
    """

    llm = LangChainLLM()
    response = await llm([system_message, HumanMessage(content=content)])

    return {"scratchpad": response}


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

    response = await model.ainvoke([system_message, HumanMessage(content=content)])

    return {"messages": [response]}


def route_condition(agent_state: AgentState) -> Literal["continue", "conclude", "end"]:
    logger = get_agent_logger("router")

    messages = agent_state.get('messages', [])
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


def route_plan_reflect(agent_state: AgentState) -> Literal["plan_reflect", "continue"]:
    """Route to the plan_reflect node every 6 steps to allow reflection on progress."""
    # If the current step is divisible by 6, route to plan_reflect
    if agent_state.get('step', 0) > 0 and agent_state.get('step', 0) % 6 == 0:
        logger.debug(
            f"Step {agent_state.get('step', 0)}: Routing to plan_reflect for periodic reflection"
        )
        return "plan_reflect"

    # Otherwise continue with normal flow
    return "continue"


graph = (
    StateGraph(AgentState)
    .add_node("browser_state_updater", browser_state_updater)
    .add_node("browser_executor", browser_executor)
    .add_node("tool_executor", tool_executor)
    .add_node("task_summarizer", task_summarizer)
    .add_node("plan_reflect", plan_reflect)
    .add_edge(START, "browser_state_updater")
    .add_edge("browser_state_updater", "browser_executor")
    .add_conditional_edges(
        "browser_executor",
        route_condition,
        {"continue": "tool_executor", "end": END, "conclude": "task_summarizer"},
    )
    .add_conditional_edges(
        "tool_executor",
        route_plan_reflect,
        {"plan_reflect": "plan_reflect", "continue": "browser_state_updater"},
    )
    .add_edge("plan_reflect", "browser_state_updater")
    .add_edge("task_summarizer", END)
    .compile(checkpointer=checkpointer)
)
