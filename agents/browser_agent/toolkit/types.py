from __future__ import annotations
import asyncio
from typing import Any, TYPE_CHECKING
from pydantic import BaseModel
from logging_utils import get_toolkit_logger

if TYPE_CHECKING:
    from browser_use.context import BrowserContext
    
    
class ActionResult(BaseModel):
    message: str | None = None
    error: str | None = None
    data: Any = None
    reserve_tools: list[str] = []

    def to_dict(self):
        return self.model_dump(exclude_none=True)
    

class FilterContext(BaseModel):
    """
    A data class holding all contextual information for filtering rules.
    """

    domain: str | None = None
    step: int | None = None
    last_action: str | None = None
    text_field_focused: bool = False
    reserved_tools: list[str] = []  # Tools reserved for the next turn only.


class ToolLogger:
    """Logs the error to the logging system, and also to the browser interface when a BrowserContext is provided."""
    
    logger = get_toolkit_logger("tools")

    @classmethod
    def _log(cls, level: str, message: str, browser_context: BrowserContext | None = None):
        if browser_context is not None:
            asyncio.create_task(browser_context.animator.log(message, level))
        else:
            getattr(cls.logger, level)(message)

    @classmethod
    def info(cls, message: str, browser_context: BrowserContext | None = None):
        cls._log("info", message, browser_context)

    @classmethod
    def error(cls, message: str, browser_context: BrowserContext | None = None):
        cls._log("error", message, browser_context)

    @classmethod
    def debug(cls, message: str, browser_context: BrowserContext | None = None):
        cls._log("debug", message, browser_context)

    @classmethod
    def warning(cls, message: str, browser_context: BrowserContext | None = None):
        cls._log("warning", message, browser_context)

