from typing import Literal, Dict, Any, List, Union
from langchain_core.messages import SystemMessage, HumanMessage, ToolMessage
from typing import TYPE_CHECKING
import json
from enum import Enum
from abc import ABC, abstractmethod
import base64
from orbit_core.browser_use.dom.types import DOMElementNode
import logging
from orbit_core.utils.logging_utils import get_message_builder_logger
from .utils import BBoxRenderer, save_to_file

if TYPE_CHECKING:
    from orbit_core.browser_use.types import BrowserState
    from .agent import AgentState


class BrowserRepresentationType(Enum):
    """The type of representation used to show the browser state to the LLM."""

    SCREENSHOT = "screenshot"
    MINIMAL_DOM_TEXT_SCREENSHOT = "minimal_dom_text_screenshot"
    MARKDOWN_DOM = "markdown_dom"
    JSON_DOM = "json_dom"


class BrowserRepresentation(ABC):
    """Base class for different ways to represent browser state to the LLM."""

    @abstractmethod
    def get_state_instructions(self) -> str:
        """Return instructions on how to interpret this state representation."""
        pass

    @abstractmethod
    def get_state_content(
        self, browser_state: "BrowserState", agent_state: "AgentState"
    ) -> dict:
        """Return the content that represents the browser state.

        Returns:
            List of content blocks specific to this state representation that will be used
            by the builder to construct the final human message.
        """
        pass


# Get logger for the Screenshot class
screenshot_logger = get_message_builder_logger("executor")


class Screenshot(BrowserRepresentation):
    """Browser state representation that uses screenshots."""

    def get_state_instructions(self) -> str:
        # TODO: where the label will be present.
        instruct1 = (
            "You will be provide with a screenshot (OCR) of the browser state. "
            "Carefully analyze its visual layout, text content and all interactive elements. "
            "Interactive elements are mapped with numbered labels (e.g., [12]) "
            "at the top-left of their bounding boxes; use them to interact with the browser."
        )

        return instruct1

    def _get_dom_text(self, state: "BrowserState") -> str:

        # 1. Generate a detailed DOM representation
        elements_text = state.element_tree.clickable_elements_to_string(
            include_attributes=[
                "title",
                "type",
                "name",
                "role",
                "tabindex",
                "aria-label",
                "placeholder",
                "value",
                "alt",
                "aria-expanded",
            ]
        )

        # --- 2. Add context about scrolling ---
        has_content_above = (state.pixels_above or 0) > 0
        has_content_below = (state.pixels_below or 0) > 0

        if elements_text:
            if has_content_above:
                elements_text = f"... {state.pixels_above} pixels above - scroll or extract content to see more ...\n{elements_text}"
            else:
                elements_text = f"[Start of page]\n{elements_text}"

            if has_content_below:
                elements_text = f"{elements_text}\n... {state.pixels_below} pixels below - scroll or extract content to see more ..."
            else:
                elements_text = f"{elements_text}\n[End of page]"
        else:
            elements_text = ""

        return elements_text

    def get_state_content(
        self, browser_state: "BrowserState", agent_state: "AgentState"
    ) -> dict:

        if not browser_state.screenshot:
            screenshot_logger.error("No screenshot available in browser state")
            raise ValueError("No screenshot available. Inside the vision context")

        base64_screenshot = browser_state.screenshot

        state_text = f"Browser: {browser_state.title}\n URL: {browser_state.url}\n"
        if len(browser_state.selector_map) == 0:
            state_text += "[No interactive elements found, looks like the page is loading.]"

        bbox_renderer = BBoxRenderer()
        # bboxes_screenshot = bbox_renderer.render_bboxes(base64_screenshot, browser_state.selector_map)
        bboxes_screenshot = browser_state.screenshot
        try:
            step = agent_state.get('step', 0)
            
            save_to_file(
                "screenshots",
                f"screenshot.png",
                base64.b64decode(bboxes_screenshot),
                index=step,
            )
            save_to_file(
                "doms",
                f"dom.txt",
                self._get_dom_text(browser_state),
                index=step,
            )

        except Exception as e:
            screenshot_logger.error(
                f"Error saving screenshot or dom text: {e}", exc_info=True
            )
            raise

        return {"text": state_text, "image": bboxes_screenshot}


class MinimalDomTextScreenshot(Screenshot):
    """Browser state representation that uses minimal DOM with screenshots.
    Inherits from Screenshot to reuse screenshot functionality.
    """

    def get_state_instructions(self) -> str:
        instruct2 = (
            "Analyze both the screenshot and DOM to understand the browser state."
            "Interactive elements are marked with bounding boxes and numbered labels (e.g., [12])."
            "Use the element's number to interact with it."
            "The minimal DOM provides additional context about the page structure."
        )
        return instruct2

    def get_state_content(
        self, browser_state: "BrowserState", agent_state: "AgentState"
    ) -> dict:
        # First get screenshot content by calling the parent class method
        screenshot_content = super().get_state_content(browser_state, agent_state)

        return {
            "image": screenshot_content,
            "text": {
                """
                Minimal DOM Structure:
                (Minimal DOM representation would go here)
                """,
            },
        }


class MarkdownDOM(BrowserRepresentation):
    """Browser state representation that uses a Markdown rendering of the DOM structure.
    Provides a clear, hierarchical view of the page structure focusing on interactive elements.
    """

    def get_state_instructions(self) -> str:
        instructions = (
            "Analyze the Markdown DOM representation to understand the page structure. "
            "Interactive elements are marked with numbered labels (e.g., [12]). "
            "Use the element's number to interact with it. "
            "The Markdown representation shows the hierarchical structure of the page, "
            "with indentation indicating parent-child relationships."
        )
        return instructions

    
    def _format_node(
        self,
        node: DOMElementNode,
        indent_level: int = 0,
        include_ids: bool = True,
        expand_non_interaction_subtree: bool = False,
        interactive_map: dict = None,
        current_index: list = None,
    ) -> str:
        """Format a DOM node as a Markdown string with hierarchical structure."""
        if interactive_map is None:
            interactive_map = {}
        if current_index is None:
            current_index = [1]  # Start with index 1

        indent = " " * indent_level

        # Start with tag name
        is_interactive = node.is_interactive or node.highlight_index is not None

        # Handle element identification
        id_str = ""
        if node.highlight_index is not None and include_ids:
            # Use the existing highlight index
            id_str = f" [{node.highlight_index}]"
            interactive_map[node.highlight_index] = node
        elif is_interactive and include_ids:
            # Auto-assign an index for interactive elements without one
            assigned_index = current_index[0]
            id_str = f" [{assigned_index}*]"  # Add * to indicate auto-assigned
            if not hasattr(node, "highlight_index") or node.highlight_index is None:
                node.highlight_index = assigned_index
            interactive_map[assigned_index] = node
            current_index[0] += 1

        # Build the result string
        result = f"{indent}{node.tag_name}{id_str}"

        # Add text content if available
        text = node.get_all_text_till_next_clickable_element()
        if len(text.strip()) > 0:
            result += f' "{text}"'

        # Add relevant attributes
        relevant_attrs = {
            key: value
            for key, value in node.attributes.items()
            if key
            in [
                "title",
                "type",
                "name",
                "role",
                "aria-label",
                "placeholder",
                "value",
                "alt",
                "href",
            ]
            and str(value) not in text  # Skip if attribute value is already in text
        }

        if relevant_attrs:
            result += " " + " ".join(
                f"{key}={value}" for key, value in relevant_attrs.items()
            )

        # Indicate interactivity
        if is_interactive:
            result += " (interactive)"

        # Recursively format children
        if len(node.children) > 0:
            result += " {\n"
            for child in node.children:
                if isinstance(child, DOMElementNode):
                    # For non-interactive elements with no highlight index,
                    # don't expand their subtree unless specified
                    if (
                        not child.is_interactive
                        and child.highlight_index is None
                        and not expand_non_interaction_subtree
                    ):
                        inner_text = child.get_all_text_till_next_clickable_element()
                        if len(inner_text.strip()) > 0:
                            result += f"{indent}  {child.tag_name}: {inner_text}\n"
                        continue

                    result += self._format_node(
                        child,
                        indent_level + 2,
                        include_ids=include_ids,
                        expand_non_interaction_subtree=expand_non_interaction_subtree,
                        interactive_map=interactive_map,
                        current_index=current_index,
                    )
            result += indent + "}\n"
        else:
            result += "\n"

        return result

    def _dom_markdown(self, browser_state: "BrowserState") -> str:
        """Convert the DOM tree to a Markdown representation."""
        if not browser_state.element_tree:
            return "No DOM content available."

        # Track interactive elements
        interactive_map = {}

        md_content = self._format_node(
            browser_state.element_tree,
            include_ids=True,
            expand_non_interaction_subtree=False,
            interactive_map=interactive_map,
        )

        # Add scrolling context
        has_content_above = (browser_state.pixels_above or 0) > 0
        has_content_below = (browser_state.pixels_below or 0) > 0

        if has_content_above:
            md_content = f"... {browser_state.pixels_above} pixels above - scroll to see more ...\n{md_content}"
        else:
            md_content = f"[Start of page]\n{md_content}"

        if has_content_below:
            md_content = f"{md_content}\n... {browser_state.pixels_below} pixels below - scroll to see more ..."
        else:
            md_content = f"{md_content}\n[End of page]"

        # Update browser_state's selector_map if needed
        if interactive_map and hasattr(browser_state, "selector_map"):
            # Only add elements that aren't already in the selector_map
            for idx, elem in interactive_map.items():
                if idx not in browser_state.selector_map:
                    browser_state.selector_map[idx] = elem

        # Note: We removed the interactive elements summary from here
        # since it's now handled in get_state_content

        return md_content

    def get_state_content(
        self, browser_state: "BrowserState", agent_state: "AgentState"
    ) -> dict:
        """Return the Markdown DOM representation of the browser state."""

        # Generate the interactive elements summary for both file and display
        interactive_summary = ""
        if hasattr(browser_state, "selector_map") and browser_state.selector_map:
            interactive_count = len(browser_state.selector_map)
            interactive_summary = f"\n\n## Interactive Elements ({interactive_count})\n"

            # Print debugging info about interactive elements (to console)
            print(f"Selector map has {interactive_count} elements")

            # Add each element to both the console output and the file content
            for idx, elem in sorted(browser_state.selector_map.items()):
                elem_desc = (
                    elem.get_description() if hasattr(elem, "get_description") else ""
                )
                # Print to console
                print(f"  Element [{idx}]: {elem.tag_name} - {elem_desc}")
                # Add to summary for file
                interactive_summary += f"- [{idx}] {elem.tag_name}: {elem_desc}\n"

            interactive_summary += (
                "\nUse these element numbers to interact with the page."
            )
        else:
            print("Selector map has 0 elements")
            interactive_summary = "\n\n## Interactive Elements (0)\nNo interactive elements were detected on this page. You may need to scroll to find interactive elements."

        # Add the interactive elements to the markdown content before saving
        markdown_content = self._dom_markdown(browser_state) + interactive_summary

        # Save the enhanced markdown representation to a file
        save_to_file(
            "agents/browser_executor/dom",
            f"dom_markdown.md",
            markdown_content.encode("utf-8"),
            index=agent_state.get('step', 0),
        )

        # Add note for the displayed text
        interactive_count = (
            len(browser_state.selector_map)
            if hasattr(browser_state, "selector_map")
            else 0
        )
        interaction_note = ""
        if interactive_count > 0:
            interaction_note = f"\n\nNOTE: There are {interactive_count} interactive elements marked with [number]. Use these numbers to interact with elements."
        else:
            interaction_note = "\n\nNOTE: No interactive elements were detected on this page. You may need to scroll to find interactive elements."

        return {
            "text": f"# DOM Structure (Markdown)\n```\n{markdown_content}\n```{interaction_note}",
        }


class JsonDOM(BrowserRepresentation):
    """Browser state representation that uses a JSON rendering of the DOM structure.
    Provides a structured view of the page suitable for LLM parsing.
    """

    def get_state_instructions(self) -> str:
        instructions = (
            "Analyze the JSON DOM representation to understand the page structure. "
            "Interactive elements have 'id' fields with their numeric labels. "
            "Use these element IDs to interact with the page. "
            "The JSON structure shows the hierarchical organization of the page with "
            "parent-child relationships represented through nested 'children' arrays."
        )
        return instructions

    def _node_to_dict(
        self,
        node: DOMElementNode,
        include_ids: bool = True,
        include_links: bool = False,
        max_depth: int = -1,
        current_depth: int = 0,
        interactive_map: dict = None,
        current_index: list = None,
    ) -> Dict[str, Any]:
        """Convert a DOM node to a dictionary representation."""
        if interactive_map is None:
            interactive_map = {}
        if current_index is None:
            current_index = [1]  # Start with index 1

        if max_depth > 0 and current_depth > max_depth:
            return {"role": "truncated", "name": "Maximum depth reached"}

        # Build the basic node dictionary
        node_dict = {
            "role": node.tag_name,
            "name": node.get_all_text_till_next_clickable_element().strip(),
        }

        # Determine if element is interactive
        is_interactive = node.is_interactive or node.highlight_index is not None

        # Add ID if available or assign one for interactive elements
        if include_ids:
            if node.highlight_index is not None:
                node_dict["id"] = node.highlight_index
                interactive_map[node.highlight_index] = node
            elif is_interactive:
                # Auto-assign an index for interactive elements without one
                assigned_index = current_index[0]
                node_dict["id"] = assigned_index
                node_dict["auto_assigned"] = True
                if not hasattr(node, "highlight_index") or node.highlight_index is None:
                    node.highlight_index = assigned_index
                interactive_map[assigned_index] = node
                current_index[0] += 1

        # Mark interactive elements
        if is_interactive:
            node_dict["interactive"] = True

        # Add relevant attributes
        relevant_attrs = {
            key: value
            for key, value in node.attributes.items()
            if key
            in [
                "title",
                "type",
                "name",
                "role",
                "aria-label",
                "placeholder",
                "value",
                "alt",
            ]
        }

        # Include href only if specified
        if include_links and "href" in node.attributes:
            relevant_attrs["href"] = node.attributes["href"]

        # Add attributes to node dict
        node_dict.update(relevant_attrs)

        # Add children recursively if they exist
        if node.children and (max_depth == -1 or current_depth < max_depth):
            node_dict["children"] = []
            for child in node.children:
                if isinstance(child, DOMElementNode):
                    child_dict = self._node_to_dict(
                        child,
                        include_ids=include_ids,
                        include_links=include_links,
                        max_depth=max_depth,
                        current_depth=current_depth + 1,
                        interactive_map=interactive_map,
                        current_index=current_index,
                    )
                    node_dict["children"].append(child_dict)

        return node_dict

    def _dom_json(
        self,
        browser_state: "BrowserState",
        include_ids: bool = True,
        include_links: bool = False,
        max_depth: int = -1,
    ) -> str:
        """Convert the DOM tree to a JSON representation."""
        if not browser_state.element_tree:
            return json.dumps({"error": "No DOM content available."})

        # Track interactive elements
        interactive_map = {}

        dom_dict = self._node_to_dict(
            browser_state.element_tree,
            include_ids=include_ids,
            include_links=include_links,
            max_depth=max_depth,
            interactive_map=interactive_map,
        )

        # Add metadata about scrolling and page
        dom_dict["metadata"] = {
            "url": browser_state.url,
            "title": browser_state.title,
            "pixels_above": browser_state.pixels_above or 0,
            "pixels_below": browser_state.pixels_below or 0,
        }

        # Add interactive elements summary
        if interactive_map:
            interactive_elements = []
            for idx, elem in sorted(interactive_map.items()):
                text = elem.get_all_text_till_next_clickable_element().strip()
                text = text[:50] + "..." if len(text) > 50 else text
                description = (
                    elem.get_description() if hasattr(elem, "get_description") else ""
                )
                interactive_elements.append(
                    {
                        "id": idx,
                        "tag": elem.tag_name,
                        "description": description or text,
                    }
                )
            dom_dict["interactive_elements"] = interactive_elements

            # Update browser_state's selector_map if needed
            if hasattr(browser_state, "selector_map"):
                # Only add elements that aren't already in the selector_map
                for idx, elem in interactive_map.items():
                    if idx not in browser_state.selector_map:
                        browser_state.selector_map[idx] = elem

        return json.dumps(dom_dict, indent=2)

    def get_state_content(
        self, browser_state: "BrowserState", agent_state: "AgentState"
    ) -> dict:
        """Return the JSON DOM representation of the browser state."""

        # Process interactive elements for both console and file
        interactive_count = (
            len(browser_state.selector_map)
            if hasattr(browser_state, "selector_map") and browser_state.selector_map
            else 0
        )

        # Print interactive elements to console
        if hasattr(browser_state, "selector_map") and browser_state.selector_map:
            print(f"Selector map has {interactive_count} elements")
            for idx, elem in sorted(browser_state.selector_map.items()):
                elem_desc = (
                    elem.get_description() if hasattr(elem, "get_description") else ""
                )
                print(f"  Element [{idx}]: {elem.tag_name} - {elem_desc}")
        else:
            print("Selector map has 0 elements")

        # Generate and save the JSON representation
        json_content = self._dom_json(
            browser_state,
            include_ids=True,
            include_links=True,
            max_depth=10,  # Limit depth to prevent overly large JSON
        )

        # Save to file
        save_to_file(
            "agents/browser_executor/dom",
            f"dom_json.json",
            json_content.encode("utf-8"),
            index=agent_state.get('step', 0),
        )

        # Add note about interactive elements for display
        interaction_note = ""
        if interactive_count > 0:
            interaction_note = f"\n\nNOTE: There are {interactive_count} interactive elements marked with 'id' fields. Use these IDs to interact with elements."
        else:
            interaction_note = "\n\nNOTE: No interactive elements were detected on this page. You may need to scroll to find interactive elements."

        return {
            "text": f"# DOM Structure (JSON)\n```json\n{json_content}\n```{interaction_note}",
        }
