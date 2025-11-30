from .schema import Assistant

system_assistants = {
    "browser_agent": Assistant(
        "browser_agent",
        config = {
            "recursion_limit": 50,
        },
        graph_id = "browser_agent",
        metadata = {
            "is_primary": True,
        },
        created_at = "system",
        updated_at = "system",
        name = "Orbit",
        description = "Your personal AI assistant that can browse the web and interact with websites on your behalf.",
    ),
    "chat_agent": Assistant(
        "chat_agent",
        config = {
            "recursion_limit": 50,
        },
        graph_id = "browser_agent",
        metadata = {
            "is_template": True,
        },
        created_at = "system",
        updated_at = "system",
        name = "chat agent",
        description = "Your personal AI assistant that can browse the web and interact with websites on your behalf.",
    )
}