from typing import Literal, Dict, Any, List, Union
from langchain_core.messages import SystemMessage, HumanMessage, ToolMessage
from typing import TYPE_CHECKING
import json
from enum import Enum
from abc import ABC, abstractmethod
from ...utils import compress_image, save_to_file, render_bboxes_on_screenshot
import base64
from browser_use.dom.types import DOMElementNode
from .browser_representation import (
    BrowserRepresentation,
    Screenshot,
    MinimalDomTextScreenshot,
    MarkdownDOM,
    JsonDOM,
    BrowserRepresentationType,
)
if TYPE_CHECKING:
    from ...agent import BrowserState, AgentState


class ExecutorMessageBuilder:
    """Factory for creating browser state representations and building messages."""

    # Shared system message template that all contexts will use
    SYSTEM_MESSAGE_TEMPLATE = """
Your persona is Orbit, an elite AI agent specializing in precise web automation.
Your mission is to analyze the state of a web context, reason about the next step, and execute the most effective tool(s) to achieve the goal.
Always provide short 'Reasoning' (plan) based on past actions and current browser state. Be precise and decisive.
Browser state:
{state_instructions}

**Guidelines:**
- Task Completion: Make sure the goal is acheived before ending the session.
- Multi-Act: Perform multiple actions in sequence if they are visible. e.g. (type(email), type(password), click(login))
"""

    additional_instructions = """
**Strategic Guidelines:**
"""
    def __init__(self, type: BrowserRepresentationType):
        """Initialize with a specific representation type."""

        self.type = type
        self.state_representation = self._create_state_representation()

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

    @staticmethod
    def get_dynamic_instructions(
        agent_state: "AgentState",
    ) -> Union[Dict[str, Any], None]:
        """Return any additional instructions based on agent state."""
        # Add condition-based instructions here
        # For example, if agent has had multiple failures, add specific guidance
        failures = agent_state.get("failures", 0)
        if failures > 2:
            return {
                "type": "text",
                "text": """
                IMPORTANT: You've encountered multiple failures. Consider:
                1. Being more precise with element selection
                2. Trying alternative approaches if the current one isn't working
                3. Breaking down complex tasks into smaller steps
                """,
            }
        return None

    def build_human_message(
        self,
        browser_state: "BrowserState",
        agent_state: "AgentState",
    ) -> HumanMessage:
        """Build the complete human message with all necessary content."""

        contents = []

        contents.append(
            {
                "type": "text",
                "text": f"Goal: {agent_state.get('goal', 'No goal provided, exit immediately.')}",
            }
        )

        # Add any additional instructions based on agent state
        # dynamic_instructions = self.get_dynamic_instructions(agent_state)
        # if dynamic_instructions:
        #     contents.append(dynamic_instructions)
        
        # FIXME: add the tabs, in minimal format.
        state_description = {
            "type": "text",
            "text": f"""
            Current Browser State of {browser_state.title}
            URL: {browser_state.url}
            """.strip(),
        }
        contents.append(state_description)

        # Get state content with the required parameters
        state_content = self.state_representation.get_state_content(
            browser_state, agent_state
        )

        if state_content:
            contents.extend(state_content)
        else:
            contents.append(
                {
                    "type": "text",
                    "text": "No state content available. Exit immediately with a warning to the user.",
                }
            )
            
        # add last two tool messages.
        contents.extend(
            [message.content for message in agent_state.get("messages", [])[-2:] if isinstance(message, ToolMessage)] 
        )
        
        contents.append({
            "type": "text",
            "text": """You are provided with user goal, browser state, and the last action taken by the agent. Decide the next action to take."""
        })

        return HumanMessage(content=contents)

    def build_system_message(self) -> SystemMessage:
        """Build the system message with state representation-specific instructions."""
        return SystemMessage(
            content=self.SYSTEM_MESSAGE_TEMPLATE.format(
                state_instructions=self.state_representation.get_state_instructions()
            )
        )

    def build_messages(
        self,
        browser_state: "BrowserState",
        agent_state: "AgentState",
    ) -> tuple[SystemMessage, HumanMessage]:
        """Build the system and human messages for the specified state representation type."""
        system_message = self.build_system_message()
        human_message = self.build_human_message(browser_state, agent_state)

        return system_message, human_message
