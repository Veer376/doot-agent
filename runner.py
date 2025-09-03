"""Runs browser agent."""
from browser_use.browser import Browser, BrowserConfig
from browser_use.context import BrowserContext, BrowserContextConfig
from agents.browser_agent.agent import graph
from agents.browser_agent.types import AgentContext, AgentState
from utils.pretty_message import pretty_message
from utils.pretty_stats import pretty_stats
import logging
from agents.llm.usage_stats import get_usage_stats
import asyncio
from logging_config import setup_logging

setup_logging()
logger = logging.getLogger("browser_agent.runner")

async def main():
    
    try:
        
        browser = Browser(config=BrowserConfig(browser_binary_path="C:/Program Files/Google/Chrome/Application/chrome.exe"))
        browser_context = await browser.new_context(config=BrowserContextConfig(highlight_elements=False))

        agent_context = AgentContext(
            thread_id=1,
            browser_context=browser_context,
        )
        agent_state = AgentState(
            messages=[],
            task="Go to whatsapp and send message to abhishek",
            step=0,
            consecutive_failures=0,
            last_actions=[],
            reserved_tools=[]
        )
        config = {
            "configurable": {
                "thread_id": 1
            },
            "recursion_limit": 50
        }

        async for event in graph.astream(input=agent_state, config=config, context=agent_context, stream_mode="values"):
            if event.get("messages", None):
                pretty_message(event.get("messages")[-1])

        final_state = graph.get_state(config=config)
        
        pretty_stats(get_usage_stats().get_stats())
        
    except Exception as e:
        logger.error(f"Error occurred: {e}")
        pretty_stats(get_usage_stats().get_stats())
        

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt as e:
        logger.info("keyboard Interrupt")
        pretty_stats(get_usage_stats().get_stats())