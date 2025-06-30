from pydantic import BaseModel, Field
from datetime import datetime
from typing import Optional, Any, Dict

class BrowserActionResult(BaseModel):
    success: bool
    message: str
    action_type: Optional[str] = None
    data: Optional[dict[str, Any]] = None
    timestamp: datetime = Field(default_factory=datetime.utcnow)

    @classmethod
    def success(cls, action_type: str, message: str, data: dict = None) -> "BrowserActionResult":
        return cls(success=True, action_type=action_type, message=message, data=data)

    @classmethod
    def failure(cls, action_type: str, message: str, error: str = None) -> "BrowserActionResult":
        return cls(success=False, action_type=action_type, message=message, error=error)
