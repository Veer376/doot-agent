from .registry import message_registry

# Register conditional messages that can be injected into the agent's system prompt
# based on specific conditions

message_registry.register(
    message="""You have had multiple failures. 
Please analyze the last action and current browser state carefully before proceeding. 
Reason about the next most appropriate action to take. 
If you think that you cannot complete the task, due to lack of tools consider the 'finish_task' tool to end the task.
""",
    is_active=lambda ctx: len(ctx.consecutive_failures) >= ctx.max_consecutive_failures,
)
