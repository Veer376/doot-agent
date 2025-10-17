from .registry import message_registry

class MessageException(BaseException):
    
    def __init__(self, message: str):
        self.message = message
        message_registry.register(
            message=message,
            is_active=lambda ctx: True
        )


class ToolCallMissing(MessageException):
    message = """
ERROR: REQUIRED TOOL CALL MISSING. 
IMMEDIATE ACTION REQUIRED: Generate a valid tool call. Explicitly use the finish tool if you intent to finish the execution.
Failure to comply will result in task incompletion.
"""
    def __init__(self, message: str|None = None):
        self.message = self.message or message
        super().__init__(self.message or message)
    
    def __str__(self):
        return f"ToolCallMissing: {self.message}"
        
        
class InvalidToolCall(MessageException):
    message="""
ERROR: INVALID TOOL CALL DETECTED.
CORRECTION REQUIRED: The parameters/schema in your last tool call are incorrect.
INSTRUCTIONS: Verify tool signature precisely and resubmit with exact parameter requirements.
"""
    def __init__(self, message: str|None = None):
        super().__init__(self.message or message)

    def __str__(self):
        return f"InvalidToolCall: {self.message}"