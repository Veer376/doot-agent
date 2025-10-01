from .schema import Assistant
import uuid

# {id: Assistant}
default_assistants = {
    "chat_agent": Assistant(
        "chat_agent",
        config={
            "recursion_limit": 100,
        },
        created_at="system",
        graph_id="chat_agent",
        metadata={
            "is_primary": True,
        },
        updated_at="system",
        name="Chat Agent",
        description="A default chat agent assistant",
    )
}