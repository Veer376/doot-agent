"""Runs browser agent."""

from orbit_core.browser_use.browser import Browser, BrowserConfig
from orbit_core.browser_use.context import BrowserContext, BrowserContextConfig
from orbit_core.agents.browser_agent.agent import graph
from orbit_core.agents.browser_agent.state import AgentContext, AgentState
from orbit_core.utils.pretty_message import pretty_message
from orbit_core.utils.pretty_stats import pretty_stats
import logging

# from tests.usage_stats import get_usage_stats
import asyncio
from orbit_core.utils.logging_config import setup_logging
from orbit_core.agents.llms import GeminiConfig
from langchain_core.messages import HumanMessage

setup_logging()
logger = logging.getLogger("browser_agent.runner")


async def main():

    try:  # 9910772493 -> Tripti
        agent_context = AgentContext(
            user_id="something"
        )
        agent_state = AgentState(
            messages=[
                HumanMessage(content="Go to whatsapp and send message to abhishek")
            ],
        )
        config = {"configurable": {"thread_id": 1}, "recursion_limit": 50}

        async for mode, event in graph.astream(
            input=agent_state,
            config=config,
            context=agent_context,
            stream_mode=["messages", "values"],
        ):
            if mode == "values":
                pretty_message(event.get("messages", [])[-1])
                # print(f"{event.get("messages", None)}")
                
        # final_state = graph.get_state(config=config)

        # pretty_stats(get_usage_stats().get_stats())

    except Exception as e:
        logger.error(f"Error occurred: {e}", traceback=True)
        # pretty_stats(get_usage_stats().get_stats())


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt as e:
        logger.info("keyboard Interrupt")
        # pretty_stats(get_usage_stats().get_stats())
