import operator
from typing import Annotated, Any, Literal, Sequence, TypedDict, TYPE_CHECKING
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
from .utils import get_model, format_message, TokenTracker
from browser_use.context import BrowserContext
from browser_use.context import BrowserState
from .message_builder import ExecutorMessageBuilder, BrowserRepresentationType
from logging_utils import get_agent_logger

llm = get_model()

logger = get_agent_logger()

class AgentState(TypedDict):
    messages: Annotated[Sequence[BaseMessage], operator.add]
    goal: str
    step: int
    consecutive_failures: list[str] | None = None
    last_action: str | None = None
    last_action_message: str | None = None
    token_usage: dict[str, int]


class BrowserAgent:
    def __init__(
        self,
        session_id: str,
        browser_context: BrowserContext,
        max_consecutive_failures: int = 3,
        browser_representation_type: BrowserRepresentationType = BrowserRepresentationType.SCREENSHOT,
    ):
        logger.info(f"Initializing BrowserAgent with session_id: {session_id}, representation: {browser_representation_type.value}")
        
        self.session_id = session_id
        self.browser_context = browser_context
        self.max_consecutive_failures = max_consecutive_failures
        self.executor_message_builder = ExecutorMessageBuilder(
            type=browser_representation_type
        )
        self.token_tracker = TokenTracker()
        self.tools_by_name = tool_registry.tools_by_name

        self.agent = self._build_agent().compile(checkpointer=InMemorySaver())

    async def _browser_executor(self, agent_state: AgentState):
        """Supervisor node that gathers context, calls the LLM, and decides the next action."""

        logger = get_agent_logger("browser_executor")
        agent_state["step"] += 1
        logger.debug(f"[Step {agent_state['step']}] Browser executor starting")

        # TODO: Handle the browser state in the tool call for multi-act logic.
        try:
            browser_state: BrowserState = await self.browser_context.get_state(
                cache_clickable_elements_hashes=True
            )
        except Exception as e:
            logger.error(f"Error gathering browser state: {e}", exc_info=True)
            return {"messages": []}

        # get tools and messages dynamically
        system_message, human_message = self.executor_message_builder.build_messages(
            browser_state, agent_state
        )
        tools = tool_registry.get_active_tools(browser_state, agent_state)
        logger.debug(f"Got {len(tools)} active tools")
        
        # FIXME: add a temperature lower then 0.5.
        response = await llm.bind_tools(tools).ainvoke([system_message, human_message])

        # Track tokens
        if hasattr(response, "usage_metadata") and response.usage_metadata:
            self.token_tracker.add_usage(**response.usage_metadata)
            logger.debug(f"Token usage updated: {response.usage_metadata}")

        return {"messages": [response]}

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

            tool_to_call = self.tools_by_name.get(tool_name)

            if not tool_to_call:
                result = f"Error: Tool '{tool_name}' not found."
                logger.error(f"Tool '{tool_name}' not found in registry")

            else:
                try:
                    logger.debug(f"Calling tool {tool_name}")
                    result = await tool_to_call(
                        **tool_call["args"], browser_context=self.browser_context
                    )

                    agent_state["last_action"] = tool_name
                    agent_state["last_action_message"] = str(result)

                except Exception as e:
                    result = f"Error executing tool {tool_name}: {e}"
                    logger.error(
                        f"Error executing tool {tool_name}: {e}", exc_info=True
                    )

            tool_results.append(
                ToolMessage(
                    content=str(result), tool_call_id=tool_call.get("id", "none")
                )
            )

        return {"messages": tool_results}

    async def run(self, goal: str, prompt: str | None = None):
        """Run the browser agent with a specified goal."""
        logger = get_agent_logger("agent_run")
        
        logger.info(f"Starting browser agent with goal: {goal}")
    
        initial_state = {
            "messages": [HumanMessage(content=prompt)] if prompt else [],
            "goal": goal,
            "step": 0,
            "consecutive_failures": [],
            "last_action": None,
            "last_action_message": None,
            "token_usage": {},
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
                    print(format_message(event["messages"][-1]))

            state_snapshot = self.agent.get_state(config)
            logger.debug("Agent stream completed")

        except Exception as e:
            logger.error(f"Error running agent stream: {e}", exc_info=True)
            raise

        logger.info(f"Agent execution completed")

        # Log token usage summary
        token_usage = self.token_tracker.get_usage()
        logger.info(f"Token usage summary: {token_usage}")

        final_state = {
            "messages": state_snapshot.values["messages"],
            "goal": state_snapshot.values["goal"],
            "token_usage": token_usage,
        }

        return final_state

    def _route_condition(self, agent_state: AgentState) -> Literal["continue", "end"]:
        logger = get_agent_logger("router")
        if agent_state["messages"]:
            last_message = agent_state["messages"][-1]
            if not isinstance(last_message, AIMessage) or not last_message.tool_calls:
                logger.info("No tool calls found, ending agent loop.")
                return "end"
            
        return "continue"

    def _build_agent(self) -> StateGraph:
        logger = get_agent_logger("graph_builder")
        logger.debug("Building agent state graph")

        builder = StateGraph(AgentState)

        builder.add_node("browser_executor", self._browser_executor)
        builder.add_node("tool_executor", self._tool_executor)

        builder.add_edge(START, "browser_executor")
        builder.add_conditional_edges(
            "browser_executor",
            self._route_condition,
            {"continue": "tool_executor", "end": END},
        )
        builder.add_edge("tool_executor", "browser_executor")

        logger.debug("Agent graph built successfully")
        return builder
