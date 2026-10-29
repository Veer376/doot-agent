"""Built-in assistant for the verified release path."""
system_assistants = {
    "chat_agent": {
        "assistant_id": "chat_agent", "graph_id": "chat_agent", "name": "Doot",
        "description": "A stateful agent with tool calls and approval before writing a report.",
        "config": {"recursion_limit": 30}, "context": {"available_models": [__import__("os").getenv("DOOT_MODEL", "google_genai:gemini-2.5-flash")], "default_model": __import__("os").getenv("DOOT_MODEL", "google_genai:gemini-2.5-flash")},
        "metadata": {"is_primary": True, "icon": "doot"},
        "created_at": "2026-10-29T00:00:00+00:00", "updated_at": "2026-10-29T00:00:00+00:00",
    }
}
