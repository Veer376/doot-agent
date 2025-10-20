from .schema import Assistant

default_assistants = {
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