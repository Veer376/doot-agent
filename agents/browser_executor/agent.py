import operator
from typing import Annotated, Any, Literal, Sequence, TypedDict, TYPE_CHECKING, Union
from urllib.parse import urlparse
from langchain_core.messages import (
    AIMessage,
    BaseMessage,
    HumanMessage,
    ToolMessage,
    SystemMessage,
)
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, StateGraph, START
from langgraph.types import Command
from pydantic import BaseModel, Field

# Dependency imports
from .toolkit.registry import tool_registry
from .utils import print_message, error_handler
from browser_use.context import BrowserContext
from browser_use.types import BrowserState
from logging_utils import get_agent_logger
from .message_builder import BrowserRepresentationType, MessageBuilder, MessageBlueprint
from ..llm import LLM, GeminiLLM, LangChainLLM, LLMConfig
from ..llm.usage_stats import get_usage_stats
from .toolkit import ActionResult

logger = get_agent_logger()


class AgentState(TypedDict):
    messages: Annotated[Sequence[BaseMessage], operator.add]
    task: str
    step: int
    consecutive_failures: list[str]
    last_action: str


class BrowserAgent:
    def __init__(
        self,
        session_id: str,
        browser_context: BrowserContext,
        max_consecutive_failures: int = 2,
        browser_representation_type: BrowserRepresentationType = BrowserRepresentationType.SCREENSHOT,
        llm: Literal["gemini", "langchain"] = "gemini",
    ):
        self.session_id = session_id
        self.browser_context = browser_context
        self.max_consecutive_failures = max_consecutive_failures
        self.message_builder = MessageBuilder(browser_representation_type)
        # Create an instance of the LLM class
        self.llm: LLM = GeminiLLM() if llm == "gemini" else LangChainLLM()
        self.tools = tool_registry.tools

        self.agent = self._build_agent().compile(checkpointer=InMemorySaver())
        
    
    async def _browser_executor(self, agent_state: AgentState):
        """Supervisor node that gathers context, calls the LLM, and decides the next action."""

        logger = get_agent_logger("browser_executor")
        logger.debug(f"[Step {agent_state['step']}] Browser executor starting")

        try:
            browser_state: BrowserState = await self.browser_context.get_state(
                cache_clickable_elements_hashes=True
            )
        except Exception as e:
            logger.error(f"Error gathering browser state: {e}", exc_info=True)
            return {"messages": []}

        message_plan = self.message_builder.build_messages(browser_state, agent_state)
        tools = await tool_registry.get_active_tools(
            self.browser_context, browser_state, agent_state
        )

        logger.debug(f"[{len(tools)}] active tools")

        response = await self.llm(message_plan, tools, config=LLMConfig(thinking_budget=1024))

        return {"messages": [response], "step": agent_state["step"] + 1}
    
    
    async def _tool_executor(self, agent_state: AgentState):
        """Custom tool node that handles tool execution."""

        logger = get_agent_logger("tool_executor")

        last_message = agent_state["messages"][-1]
        tool_results = []

        # Log the number of tool calls
        tool_calls = (
            last_message.tool_calls if hasattr(last_message, "tool_calls") else []
        )

        # FIXME: Check if the browser state has been changed since the last action.
        for tool_call in tool_calls:
            tool_name = tool_call["name"]
            logger.debug(
                f"Executing tool: {tool_name} with args: {tool_call.get('args', {})}"
            )

            tool_to_call = self.tools.get(tool_name)

            result: ActionResult = await tool_to_call(
                **tool_call["args"], browser_context=self.browser_context
            )

            if hasattr(result, "error"):
                agent_state["consecutive_failures"].append(result.error)
            else:
                agent_state["consecutive_failures"].clear()

            tool_results.append(
                ToolMessage(
                    name=tool_name,
                    content=[result.to_dict()], # content: Union[str, list[str, dict]]
                    tool_call_id=tool_call.get("id"),
                )
            )

        return {"messages": tool_results, "last_action": tool_name}

    async def _task_summarizer(self, agent_state: AgentState):
        """Summarizes the task and prepares the final message for the user."""

        system_message = SystemMessage(
            content="""
                You are a task summarizer. Your job is to summarize the task and prepare the final response for the user in first person.
                You may be provided with some last messages, reason of task finish and extracted data.
                Provide the user with the descriptive summary of the task and the final result.
                """
        )
        content = [
            {"type": "text", "text": f"Last messages: {agent_state['messages'][-2:]}"},
            {"type": "text", "text": f"Task: {agent_state['task']}"},
        ]
        
        llm = LangChainLLM()
        response = await llm([system_message, HumanMessage(content=content)])

        return {"messages": [response]}

    async def run(self, task: str, prompt: str | None = None):
        """Run the browser agent with a specified task."""
        logger = get_agent_logger("agent_run")

        logger.info(f"Starting browser agent with task: {task}")

        initial_state = {
            "messages": [HumanMessage(content=prompt)] if prompt else [],
            "task": task,
            "step": 0,
            "consecutive_failures": [],
            "last_tool_call": None,
        }

        config = {
            "configurable": {"thread_id": self.session_id},
            "recursion_limit": 100,
        }

        final_state = None

        try:
            logger.debug("Starting agent stream")
            async for event in self.agent.astream(
                initial_state, config=config, stream_mode="values"
            ):
                # TODO: Send ai messages to the browser UI using javascript code.
                if event["messages"]:
                    print_message(event["messages"][-1])

            state_snapshot = self.agent.get_state(config)
            logger.debug("Agent stream completed")

        except Exception as e:
            logger.error(f"Error running agent stream: {e}", exc_info=True)
            raise

        logger.info(f"Agent execution completed")

        # Get token usage from global stats
        usage_stats = get_usage_stats()
        usage_stats = usage_stats.get_stats()
        logger.info(f"Token usage summary: {usage_stats}")

        final_state = {
            "messages": state_snapshot.values["messages"],
            "task": state_snapshot.values["task"],
            "usage_stats": usage_stats,
        }

        return final_state

    def _route_condition(
        self, agent_state: AgentState
    ) -> Literal["continue", "conclude", "end"]:
        logger = get_agent_logger("router")

        messages = agent_state.get("messages", None)
        last_message = messages[-1] if messages else None

        if isinstance(last_message, AIMessage) and hasattr(last_message, "tool_calls") and last_message.tool_calls:
            tool_call = last_message.tool_calls[0]

            if tool_call.get("name") == "finish_task":
                logger.debug("Finish task tool called, concluding /Ending task.")
                return "end"

        return "continue"

    def _build_agent(self) -> StateGraph:
        logger = get_agent_logger("graph_builder")
        logger.debug("Building agent state graph")

        builder = StateGraph(AgentState)

        builder.add_node("browser_executor", self._browser_executor)
        builder.add_node("tool_executor", self._tool_executor)
        builder.add_node("task_summarizer", self._task_summarizer)

        builder.add_edge(START, "browser_executor")
        builder.add_conditional_edges(
            "browser_executor",
            self._route_condition,
            {"continue": "tool_executor", "end": END, "conclude": "task_summarizer"},
        )
        builder.add_edge("tool_executor", "browser_executor")
        builder.add_edge("task_summarizer", END)

        logger.debug("Agent graph built successfully")
        return builder
