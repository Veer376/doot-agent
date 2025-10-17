"""Runs browser agent."""

from core.browser_use.browser import Browser, BrowserConfig
from core.browser_use.context import BrowserContext, BrowserContextConfig
from core.agents.browser_agent.agent import graph
from core.agents.browser_agent.state import AgentContext, AgentState
from core.utils.pretty_message import pretty_message
from core.utils.pretty_stats import pretty_stats
import logging

# from tests.usage_stats import get_usage_stats
import asyncio
from core.utils.logging_config import setup_logging
from core.agents.llm import LLMConfig
from langchain_core.messages import HumanMessage

setup_logging()
logger = logging.getLogger("browser_agent.runner")


async def main():

    try:  # 9910772493 -> Tripti
        agent_context = AgentContext(
            thread_id=1, llm="gemini", llm_config=LLMConfig(thinking_budget=-1)
        )
        agent_state = AgentState(
            messages=[
                HumanMessage(content="Go to whatsapp and send message to abhishek")
            ],
            task="Go to whatsapp and send message to abhishek",
            step=0,
            consecutive_failures=[],
            reserved_tools=[],
        )
        config = {"configurable": {"thread_id": 1}, "recursion_limit": 50}

        async for mode, event in graph.astream(
            input=agent_state,
            config=config,
            context=agent_context,
            stream_mode=["messages", "updates"],
        ):
            print(f"{mode}: {event}")
            
        # final_state = graph.get_state(config=config)

        # pretty_stats(get_usage_stats().get_stats())

    except Exception as e:
        logger.error(f"Error occurred: {e}")
        # pretty_stats(get_usage_stats().get_stats())


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt as e:
        logger.info("keyboard Interrupt")
        # pretty_stats(get_usage_stats().get_stats())
