from typing import TYPE_CHECKING
from langchain_core.messages import SystemMessage, HumanMessage, ToolMessage, AIMessage
from abc import ABC
from .perception import (
    BrowserRepresentation,
    Screenshot,
    MinimalDomTextScreenshot,
    MarkdownDOM,
    JsonDOM,
    BrowserRepresentationType,
)
from logging_utils import get_message_builder_logger
from .types import MessageBlueprint
from .messages.messages import message_registry
from .toolkit.registry import tool_registry

if TYPE_CHECKING:
    from browser_use.types import BrowserState
    from .agent import AgentState, AgentContext

logger = get_message_builder_logger("executor")


class MessageBuilder(ABC):
    """Base class for message builders."""

    SYSTEM_MESSAGE_TEMPLATE = """
You are orbit, developed by an developer 'aryaveer'. You are an expert web automation AI agent, equipped with advanced low-level automation tools for executing complex browser operations with exceptional precision.
Accomplish the user task through systematic browser state analysis and precise execution of the appropriate automation tools.

**Browser State**
{state_instructions}

When thinking: 
ALWAYS begin by concisely summarizing the task progress, referencing prior actions taken and their outcomes. 
Then assess the current browser state in detail. 
Based on this assessment, determine the next optimal action, specifying the exact tool to use, its required parameters, and the expected results from executing it.

**Guidelines**
* Use multiple actions that is parallel function calls if they are visible and logical.
* Use the finish_task tool to end the session. In case of incomplete task always include the next action you intended to perform and missing tool(s) that would have been needed to execute it."""

    # Additional instructions, usage discouraged.
    "In particular, consider whether the task is already done."

    def __init__(self, type: BrowserRepresentationType = BrowserRepresentationType.SCREENSHOT):
        """Initialize with a specific representation type."""

        self.type = type
        self.state_representation = self._create_state_representation()
        self.message_blueprint = MessageBlueprint()

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
        self.message_blueprint.system_message = system_message

    def build_ai_and_tool_messages(self, agent_state: "AgentState"):
        """Build the AI and tool messages."""

        messages = agent_state.messages

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

        self.message_blueprint.ai_message = ai_message
        self.message_blueprint.tool_messages = tool_messages

    async def build_human_messages(
        self, agent_context: "AgentContext", agent_state: "AgentState"
    ):

        # Browser State Content
        try:
            browser_state: BrowserState = await agent_context.browser_context.get_state(
                cache_clickable_elements_hashes=True
            )
        except Exception as e:
            logger.error(f"Error gathering browser state: {e}", exc_info=True)
            raise

        state_content = self.state_representation.get_state_content(
            browser_state, agent_state
        )

        if state_content:
            if "text" in state_content and state_content["text"]:
                self.message_blueprint.browser_state_text = state_content["text"]

            if "image" in state_content and state_content["image"]:
                self.message_blueprint.browser_state_image = state_content["image"]

            else:
                raise ValueError(
                    "Browser state content must include either 'text' or 'image'."
                )
        else:
            raise ValueError("Browser state content is empty or invalid.")

        # Task
        self.message_blueprint.task = agent_state.task

        # Dynamic Messages (if any)
        dynamic_messages = ""

        active_messages = message_registry.get_active_messages(agent_state)

        if active_messages:
            dynamic_messages += "**Heads-Up:**\n" + "\n".join(active_messages)

        if dynamic_messages:
            self.message_blueprint.dynamic_messages = dynamic_messages

    async def build_message_blueprint(
        self,
        agent_context: "AgentContext",
        agent_state: "AgentState",
    ) -> MessageBlueprint:

        self.build_system_message()

        self.build_ai_and_tool_messages(agent_state)

        await self.build_human_messages(agent_context, agent_state)

        tools = await tool_registry.get_active_tools(agent_context, agent_state)
        self.message_blueprint.active_tools = tools

        return self.message_blueprint
