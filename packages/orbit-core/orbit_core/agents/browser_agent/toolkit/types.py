from __future__ import annotations
import asyncio
from typing import Any, TYPE_CHECKING
from pydantic import BaseModel
from orbit_core.utils.logging_utils import get_toolkit_logger
from typing import Literal, Union

class FilterContext(BaseModel):
    """
    A data class holding all contextual information for filtering rules.
    """

    domain: str | None = None
    step: int | None = None
    last_actions: list[str] | None = None
    reserved_tools: list[str] = []  # Tools reserved for the next turn only.

