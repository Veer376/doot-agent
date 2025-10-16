from __future__ import annotations
import asyncio
from typing import Any, TYPE_CHECKING
from pydantic import BaseModel
from core.utils.logging_utils import get_toolkit_logger
from typing import Literal, Union

    
class ToolResult(BaseModel):
    message: str
    status: Literal["success", "error"] = "success"
    data: Any = None # Only include a serializable object.
    reserve_tools: list[str] | None = None
    
    def to_dict(self):
        # Exclude the None and reserve_tools.
        return self.model_dump(exclude_none=True, exclude={"reserve_tools"})
    

class FilterContext(BaseModel):
    """
    A data class holding all contextual information for filtering rules.
    """

    domain: str | None = None
    step: int | None = None
    last_action: str | None = None # FIXME: last action -> last actions
    reserved_tools: list[str] = []  # Tools reserved for the next turn only.

