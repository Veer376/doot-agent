from typing import Literal, Dict, Any, List, Union, TYPE_CHECKING
from langchain_core.messages import SystemMessage, HumanMessage, ToolMessage, AIMessage
import json
from enum import Enum
from abc import ABC, abstractmethod
from ..utils import compress_image, save_to_file, render_bboxes_on_screenshot
import base64
from ..perception import (
    BrowserRepresentation,
    Screenshot,
    MinimalDomTextScreenshot,
    MarkdownDOM,
    JsonDOM,
    BrowserRepresentationType,
)
from logging_utils import get_message_builder_logger
from .blueprint import MessageBlueprint
from ..messages.messages import message_registry

if TYPE_CHECKING:
    from browser_use.types import BrowserState
    from ..agent import AgentState

logger = get_message_builder_logger("executor")


class MessageBuilder(ABC):
    """Base class for message builders."""

    SYSTEM_MESSAGE_TEMPLATE = """
You are an expert web automation AI agent, equipped with advanced low-level automation tools for executing complex browser operations with exceptional precision.
Accomplish the user task through systematic browser state analysis and precise execution of the appropriate automation tools.

**Browser State**
{state_instructions}

When thinking: 
ALWAYS begin by concisely summarizing the task progress, referencing prior actions taken and their outcomes. 
Then assess the current browser state in detail. 
Based on this assessment, determine the next optimal action, specifying the exact tool to use, its required parameters, and the expected results from executing it.

**Guidelines**
* Use multiple actions in sequence if they are visible and logical.
"""

    # Additional instructions, usage discouraged.
    "In particular, consider whether the task is already done."

    def __init__(self, type: BrowserRepresentationType):
        """Initialize with a specific representation type."""

        self.type = type
        self.state_representation = self._create_state_representation()
        self.message_plan = MessageBlueprint()

    def _create_state_representation(self) -> BrowserRepresentation:
        """Create a BrowserRepresentation instance based on the specified type."""
        if self.type == BrowserRepresentationType.SCREENSHOT:
            return Screenshot()

        elif self.type == BrowserRepresentationType.MINIMAL_DOM_TEXT_SCREENSHOT:
            return MinimalDomTextScreenshot()

        elif self.type == BrowserRepresentationType.MARKDOWN_DOM:
            return MarkdownDOM()

        elif self.type == BrowserRepresentationType.JSON_DOM:
            return JsonDOM()

        else:
            raise ValueError(f"Unknown representation type: {self.type}")

    def build_system_message(self):
        """Return the system message with dynamic instructions."""

        system_message = self.SYSTEM_MESSAGE_TEMPLATE.format(
            state_instructions=self.state_representation.get_state_instructions()
        )
        self.message_plan.system_message = system_message

    def build_ai_and_tool_messages(self, agent_state: "AgentState"):
        """Build the AI and tool messages."""

        messages = agent_state.get("messages", [])

        ai_message_index = next(
            (
                i
                for i in range(len(messages) - 1, -1, -1)
                if isinstance(messages[i], AIMessage)
            ),
            None,
        )

        if ai_message_index is None:
            logger.warning("No AIMessage found in the agent state messages.")
            return

        ai_message = messages[ai_message_index]

        tool_messages = [
            msg
            for msg in messages[ai_message_index + 1 :]
            if isinstance(msg, ToolMessage)
        ]

        self.message_plan.ai_message = ai_message
        self.message_plan.tool_messages = tool_messages

    def build_human_messages(
        self, browser_state: "BrowserState", agent_state: "AgentState"
    ):

        # Browser State Content
        state_content = self.state_representation.get_state_content(
            browser_state, agent_state
        )

        if state_content:
            if "text" in state_content and state_content["text"]:
                self.message_plan.browser_state_text = state_content["text"]

            if "image" in state_content and state_content["image"]:
                self.message_plan.browser_state_image = state_content["image"]

            else:
                raise ValueError(
                    "Browser state content must include either 'text' or 'image'."
                )
        else:
            raise ValueError("Browser state content is empty or invalid.")

        # Task
        self.message_plan.task = agent_state.get(
            "task", "No task provided. Exit immediately."
        )

        # Dynamic Messages (if any)
        dynamic_messages = ""

        active_messages = message_registry.get_active_messages(agent_state)

        if active_messages:
            dynamic_messages += "**Heads-Up:**\n" + "\n".join(active_messages)
        
        if dynamic_messages:
            self.message_plan.dynamic_messages = dynamic_messages


    def build_messages(
        self,
        browser_state: "BrowserState",
        agent_state: "AgentState",
    ) -> MessageBlueprint:

        self.build_system_message()

        self.build_ai_and_tool_messages(agent_state)

        self.build_human_messages(browser_state, agent_state)

        return self.message_plan
