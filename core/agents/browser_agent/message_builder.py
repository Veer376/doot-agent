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
from core.utils.logging_utils import get_message_builder_logger
from .messages.messages import message_registry
from .toolkit.registry import tool_registry

if TYPE_CHECKING:
    from core.browser_use.types import BrowserState
    from core.agents.browser_agent.agent import AgentState, AgentContext

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
* Use the commit tool in parallel to record the every action and any adaptations or fallbacks made based on the current state. This helps track when a task required a deviation to ensure completion.
For example: commit(type="Adaptation", message="Filtered job search using 24 hours due to unavailability of 3 hours filter.")
* Use the finish_task tool to end the session. In case of incomplete task always include the next action you intended to perform and missing tool(s) that would have been needed to execute it."""

    # Additional instructions, usage discouraged.
    "In particular, consider whether the task is already done."

    def __init__(
        self, type: BrowserRepresentationType = BrowserRepresentationType.SCREENSHOT
    ):
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

    async def get_context(
        self,
        agent_state: "AgentState",
    ) -> list:

        contents = []

        # System Prompt
        contents.append(
            SystemMessage(
                content=self.SYSTEM_MESSAGE_TEMPLATE.format(
                    state_instructions=self.state_representation.get_state_instructions()
                )
            )
        )

        messages = agent_state.get("messages", [])

        # Human Message
        contents.extend([msg for msg in messages if isinstance(msg, HumanMessage)][-2:])

        ## Browser State NOTE: we are passing the browser state as human message.
        snapshot = agent_state.get("browser_snapshot", {}) or {}
        snapshot_content = []

        url = snapshot.get("url")
        if url:
            snapshot_content.append({"type": "text", "text": url})

        screenshot = snapshot.get("screenshot")
        if screenshot:
            snapshot_content.append(
                {
                    "type": "image_url",
                    "image_url": {"url": f"data:image/jpeg;base64,{screenshot}"},
                }
            )

        dom_text = snapshot.get("dom_text")
        if dom_text:
            snapshot_content.append({"type": "text", "text": dom_text})

        if snapshot_content:
            contents.append(HumanMessage(content=snapshot_content))

        ## TODO: Dynamic instructions.

        # AI messages FIXME: exclude the thinking part from the content later.
        contents.extend([msg for msg in messages if isinstance(msg, AIMessage)][-3:])

        # Tool messages
        contents.extend([msg for msg in messages if isinstance(msg, ToolMessage)][-3:])

        return contents
