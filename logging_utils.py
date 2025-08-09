import logging

# Base namespace constants
TOOLKIT_LOGGER_NAMESPACE = "toolkit"
MESSAGE_BUILDER_LOGGER_NAMESPACE = "message_builder"
AGENT_LOGGER_NAMESPACE = "agent"
LLM_LOGGER_NAMESPACE = "llm"


def get_toolkit_logger(component_name: str | None = None):
    """Get a logger for toolkit components."""
    return logging.getLogger(f"{TOOLKIT_LOGGER_NAMESPACE}.{component_name}")


def get_message_builder_logger(component_name: str | None = None):
    """Get a logger for message builder components."""
    if component_name:
        return logging.getLogger(
            f"{MESSAGE_BUILDER_LOGGER_NAMESPACE}.{component_name}"
        )
    return logging.getLogger(f"{MESSAGE_BUILDER_LOGGER_NAMESPACE}")


def get_agent_logger(agent_node: str | None = None):
    """Get a logger for agent nodes."""
    return logging.getLogger(
        f"{AGENT_LOGGER_NAMESPACE}.{agent_node}"
        if agent_node
        else AGENT_LOGGER_NAMESPACE
    )


def get_llm_logger(llm_type: str):
    """
    Get a logger for LLM components.

    Args:
        llm_type: The type of LLM (e.g., 'gemini', 'gpt4', 'anthropic', etc.)

    Returns:
        A logger instance with the appropriate namespace (llm.<llm_type>)
    """
    return logging.getLogger(f"{LLM_LOGGER_NAMESPACE}.{llm_type}")
