from __future__ import annotations
import logging
import asyncio
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from core.browser_use.context import BrowserContext

# Base namespace constants
TOOLKIT_LOGGER_NAMESPACE = "toolkit"
MESSAGE_BUILDER_LOGGER_NAMESPACE = "message_builder"
AGENT_LOGGER_NAMESPACE = "agent"
LLM_LOGGER_NAMESPACE = "llm"


class BrowserLogger:
    """Logs the error to the logging system, and also to the browser interface when a BrowserContext is provided."""

    def __init__(self, logger: logging.Logger):
        """Initializes the BrowserLogger with a logger instance."""
        self.logger = logger

    def _log(
        self,
        level: str,
        message: str,
        browser_context: BrowserContext | None = None,
        **kwargs,
    ):

        if browser_context is not None and hasattr(browser_context, "animator"):
            try:
                # Try to get running event loop
                loop = asyncio.get_running_loop()
                # Only create a task if we have a running loop
                if loop.is_running():
                    asyncio.create_task(browser_context.animator.log(message, level))
            except RuntimeError:
                # No running event loop, just log the message without animation
                pass

        getattr(self.logger, level)(message, **kwargs)

    def info(
        self, message: str, browser_context: BrowserContext | None = None, **kwargs
    ):
        self._log("info", message, browser_context, **kwargs)

    def error(
        self, message: str, browser_context: BrowserContext | None = None, **kwargs
    ):
        self._log("error", message, browser_context, **kwargs)

    def debug(
        self, message: str, browser_context: BrowserContext | None = None, **kwargs
    ):
        self._log("debug", message, browser_context, **kwargs)

    def warning(
        self, message: str, browser_context: BrowserContext | None = None, **kwargs
    ):
        self._log("warning", message, browser_context, **kwargs)

    def critical(
        self, message: str, browser_context: BrowserContext | None = None, **kwargs
    ):
        self._log("critical", message, **kwargs)


def _make_logger(namespace: str, component_name: str | None = None) -> BrowserLogger:
    name = f"{namespace}.{component_name}" if component_name else namespace
    return BrowserLogger(logging.getLogger(name))


get_toolkit_logger = lambda comp=None: _make_logger(TOOLKIT_LOGGER_NAMESPACE, comp)
get_agent_logger = lambda node=None: _make_logger(AGENT_LOGGER_NAMESPACE, node)
get_message_builder_logger = lambda comp=None: _make_logger(
    MESSAGE_BUILDER_LOGGER_NAMESPACE, comp
)
get_llm_logger = lambda llm_type: _make_logger(LLM_LOGGER_NAMESPACE, llm_type)
