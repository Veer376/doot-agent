from .schema import Assistant

default_assistants = {
    "chat_mode": Assistant(
        "chat_mode", # assistantId is the graph id for default assistants.
        config = {
            "recursion_limit": 10,
        },
        graph_id = "chat_mode",
        metadata = {
            "is_default": True,
            "is_primary": False,
        },
        created_at = "system",
        updated_at = "system",
        name = "Chat Mode",
        description = "A simple chat assistant that can engage in general conversations.",
    ),
    "browser_agent": Assistant(
        "browser_agent",
        config = {
            "recursion_limit": 50,
        },
        graph_id = "browser_agent",
        metadata = {
            "is_default": True,
        },
        created_at = "system",
        updated_at = "system",
        name = "Orbit",
        description = "Your personal AI assistant that can browse the web and interact with websites on your behalf.",
    )
}