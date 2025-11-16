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
    ),
    "chat_mode": Assistant(
        "chat_mode",
        config = {
            "recursion_limit": 50,
        },
        graph_id = "browser_agent",
        metadata = {
            "is_primary": True,
        },
        created_at = "system",
        updated_at = "system",
        name = "chat agent",
        description = "Your personal AI assistant that can browse the web and interact with websites on your behalf.",
    ),
    "supervisor_agent": Assistant(
        "supervisor_agent",
        config = {
            "recursion_limit": 50,
        },
        graph_id = "supervisor_agent",
        metadata = {
            # "created_by": "system",
        },
        created_at = "system",
        updated_at = "system",
        name = "Supervisor Agent",
        description = "Your personal AI assistant that supervises and delegates tasks to other agents.",
    )
}