from dataclasses import dataclass, field
from functools import cached_property
from typing import TYPE_CHECKING, Optional

from .history_tree_processor.types import HashedDomElement
from ..utils import time_execution_sync


# Simple bounding box class for drawing elements
class BoundingBox:
    x: int  # x coordinate of the top-left corner
    y: int  # y coordinate of the top-left corner
    width: int
    height: int
    highlight_index: int | None = None
    scroll_x: int = 0
    scroll_y: int = 0
    viewport_width: int = 0
    viewport_height: int = 0
    device_pixel_ratio: float = 1.0
    iframe_offset_x: int = 0
    iframe_offset_y: int = 0

    # Make the object iterable to support unpacking like x, y, width, height = bbox
    def __iter__(self):
        """Allow the object to be unpacked like a tuple (x, y, width, height)"""
        yield self.x
        yield self.y
        yield self.width
        yield self.height

    def __init__(
        self,
        x: int,
        y: int,
        width: int,
        height: int,
        highlight_index: int = None,
        scroll_x: int = 0,
        scroll_y: int = 0,
        viewport_width: int = 0,
        viewport_height: int = 0,
        device_pixel_ratio: float = 1.0,
        iframe_offset_x: int = 0,
        iframe_offset_y: int = 0,
    ):
        self.x = x
        self.y = y
        self.width = width
        self.height = height
        self.highlight_index = highlight_index
        self.scroll_x = scroll_x
        self.scroll_y = scroll_y
        self.viewport_width = viewport_width
        self.viewport_height = viewport_height
        self.device_pixel_ratio = device_pixel_ratio
        self.iframe_offset_x = iframe_offset_x
        self.iframe_offset_y = iframe_offset_y

    @property
    def absolute_x(self) -> int:
        """Get x position with iframe offset applied"""
        return self.x + self.iframe_offset_x

    @property
    def absolute_y(self) -> int:
        """Get y position with iframe offset applied"""
        return self.y + self.iframe_offset_y

    def to_dict(self) -> dict:
        return {
            "x": self.x,
            "y": self.y,
            "width": self.width,
            "height": self.height,
            "highlight_index": self.highlight_index,
            "scroll_x": self.scroll_x,
            "scroll_y": self.scroll_y,
            "viewport_width": self.viewport_width,
            "viewport_height": self.viewport_height,
            "device_pixel_ratio": self.device_pixel_ratio,
            "iframe_offset_x": self.iframe_offset_x,
            "iframe_offset_y": self.iframe_offset_y,
        }


# Avoid circular import issues
if TYPE_CHECKING:
    from .types import DOMElementNode


@dataclass(frozen=False)
class DOMBaseNode:
    is_visible: bool
    # Use None as default and set parent later to avoid circular reference issues
    parent: Optional["DOMElementNode"]

    def __json__(self) -> dict:
        raise NotImplementedError("DOMBaseNode is an abstract class")


@dataclass(frozen=False)
class DOMTextNode(DOMBaseNode):
    text: str
    type: str = "TEXT_NODE"

    def has_parent_with_highlight_index(self) -> bool:
        current = self.parent
        while current is not None:
            # stop if the element has a highlight index (will be handled separately)
            if current.highlight_index is not None:
                return True

            current = current.parent
        return False

    def is_parent_in_viewport(self) -> bool:
        if self.parent is None:
            return False
        return self.parent.is_in_viewport

    def is_parent_top_element(self) -> bool:
        if self.parent is None:
            return False
        return self.parent.is_top_element

    def __json__(self) -> dict:
        return {
            "text": self.text,
            "type": self.type,
        }


@dataclass(frozen=False)
class DOMElementNode(DOMBaseNode):
    """
    xpath: the xpath of the element from the last root node (shadow root or iframe OR document if no shadow root or iframe).
    To properly reference the element we need to recursively switch the root node until we find the element (work you way up the tree with `.parent`)
    """

    tag_name: str
    xpath: str
    attributes: dict[str, str]
    children: list[DOMBaseNode]
    is_interactive: bool = False
    is_top_element: bool = False
    is_in_viewport: bool = False
    shadow_root: bool = False
    highlight_index: int | None = None
    bbox: BoundingBox | None = None

    """
	### State injected by the browser context.

	The idea is that the clickable elements are sometimes persistent from the previous page -> tells the model which objects are new/_how_ the state has changed
	"""
    is_new: bool | None = None

    def __json__(self) -> dict:
        return {
            "tag_name": self.tag_name,
            "xpath": self.xpath,
            "attributes": self.attributes,
            "is_visible": self.is_visible,
            "is_interactive": self.is_interactive,
            "is_top_element": self.is_top_element,
            "is_in_viewport": self.is_in_viewport,
            "shadow_root": self.shadow_root,
            "highlight_index": self.highlight_index,
            "bbox": self.bbox.__dict__ if self.bbox else None,
            "children": [child.__json__() for child in self.children],
        }

    def __repr__(self) -> str:
        tag_str = f"<{self.tag_name}"

        # Add attributes
        for key, value in self.attributes.items():
            tag_str += f' {key}="{value}"'
        tag_str += ">"

        # Add extra info
        extras = []
        if self.is_interactive:
            extras.append("interactive")
        if self.is_top_element:
            extras.append("top")
        if self.shadow_root:
            extras.append("shadow-root")
        if self.highlight_index is not None:
            extras.append(f"highlight:{self.highlight_index}")
        if self.is_in_viewport:
            extras.append("in-viewport")

        if extras:
            tag_str += f' [{", ".join(extras)}]'

        return tag_str

    @cached_property
    def hash(self) -> HashedDomElement:
        from browser_use.dom.history_tree_processor.service import (
            HistoryTreeProcessor,
        )

        return HistoryTreeProcessor._hash_dom_element(self)

    def get_all_text_till_next_clickable_element(self, max_depth: int = -1) -> str:
        text_parts = []

        def collect_text(node: DOMBaseNode, current_depth: int) -> None:
            if max_depth != -1 and current_depth > max_depth:
                return

            # Skip this branch if we hit a highlighted element (except for the current node)
            if (
                isinstance(node, DOMElementNode)
                and node != self
                and node.highlight_index is not None
            ):
                return

            if isinstance(node, DOMTextNode):
                text_parts.append(node.text)
            elif isinstance(node, DOMElementNode):
                for child in node.children:
                    collect_text(child, current_depth + 1)

        collect_text(self, 0)
        return "\n".join(text_parts).strip()

    # In your dom/types.py file, add this new method to the DOMElementNode class

    # ... (inside the DOMElementNode class) ...
    def get_simplified_dom_text(self) -> str:
        """
        Recursively converts the DOM tree into a simplified, indented text
        format that is lightweight and contextually rich for an LLM.
        """
        # These are the attributes we want to show the LLM.
        # We prioritize semantic attributes over styling.
        attrs_to_keep = [
            "id",
            "class",
            "role",
            "aria-label",
            "placeholder",
            "alt",
            "for",
            "name",
            "title",
            "type",
            "href",
        ]

        # A list to hold the lines of the final text output.
        simplified_lines = []

        def process_node(node: DOMBaseNode, depth: int) -> None:
            indent = "  " * depth  # Indentation for hierarchy

            if isinstance(node, DOMTextNode):
                # Only include non-empty, visible text nodes.
                text = node.text.strip()
                if text and node.is_visible:
                    simplified_lines.append(f'{indent}"{text}"')
                return

            if isinstance(node, DOMElementNode):
                # --- Build the opening tag with important attributes ---
                attr_parts = []

                # Add the special clickable element ID if it exists.
                if node.highlight_index is not None:
                    attr_parts.append(f'id="[{node.highlight_index}]"')

                for attr, value in node.attributes.items():
                    # Ensure value is a string and not empty
                    if attr in attrs_to_keep and isinstance(value, str) and value:
                        # Clean up long class lists for brevity
                        if attr == "class" and len(value) > 50:
                            value = " ".join(value.split()[:5]) + "..."
                        attr_parts.append(f'{attr}="{value}"')

                attr_str = " ".join(attr_parts)
                simplified_lines.append(f"{indent}<{node.tag_name} {attr_str}>")

                # --- Recursively process all child nodes ---
                for child in node.children:
                    process_node(child, depth + 1)

                simplified_lines.append(f"{indent}</{node.tag_name}>")

        # Start the process from the root node (self).
        process_node(self, 0)
        return "\n".join(simplified_lines)

    def get_contextual_dom_text(
        self,
        ancestor_levels: int = 1,  # How many levels to go up
        sibling_count: int = 0,  # How many siblings to include on each side
    ) -> str:
        """
        Creates a rich, contextual, simplified DOM text snippet around a target element.

        This function implements the "vertical slice" strategy:
        1. Finds the target element by its index.
        2. Traverses UP the DOM tree by `ancestor_levels`.
        3. From that ancestor, it reconstructs a partial tree that includes:
            - The ancestor itself.
            - A few of the ancestor's siblings (`sibling_count`).
            - The full hierarchy back DOWN to the original target element.

        This provides a highly focused yet contextually rich snippet for the helper LLM.

        Args:
            target_index: The highlight_index of the example element.
            selector_map: The map of highlight_index to DOMElementNode.
            ancestor_levels: The number of parent levels to traverse upwards.
            sibling_count: The number of siblings to include on each side of the ancestor.

        Returns:
            A string containing the simplified text representation of the rich snippet.
        """

        # 1. Traverse UP to find the main ancestor
        ancestor = self
        for _ in range(ancestor_levels):
            if ancestor.parent:
                ancestor = ancestor.parent
            else:
                break  # Stop if we reach the top of the tree

        # 2. Get the parent of the final ancestor to find its siblings
        top_level_parent = ancestor.parent
        if not top_level_parent:
            # If the ancestor is the root, just render the whole tree from there
            return ancestor.get_simplified_dom_text()

        # 3. Create a new root for our snippet (the "grandparent")
        snippet_root = DOMElementNode(
            tag_name=top_level_parent.tag_name,
            attributes=top_level_parent.attributes,
            children=[],
            xpath=top_level_parent.xpath,
            is_visible=top_level_parent.is_visible,
            parent=None,
        )

        # 4. Find the ancestor's position among its siblings
        try:
            ancestor_index = top_level_parent.children.index(ancestor)
        except ValueError:
            # Fallback if something is wrong with the tree structure
            return ancestor.get_simplified_dom_text()

        # 5. Add the ancestor and its immediate siblings to the snippet
        start = max(0, ancestor_index - sibling_count)
        end = min(len(top_level_parent.children), ancestor_index + sibling_count + 1)

        for i in range(start, end):
            sibling = top_level_parent.children[i]
            # We only need the full detail for the branch containing our target
            if sibling is ancestor:
                snippet_root.children.append(ancestor)
            else:
                # For other siblings, we can create a simplified "stub" to save tokens
                stub_sibling = DOMElementNode(
                    tag_name=sibling.tag_name,
                    attributes=sibling.attributes,
                    children=[],  # Don't include children of siblings
                    xpath=sibling.xpath,
                    is_visible=sibling.is_visible,
                    parent=snippet_root,
                )
                snippet_root.children.append(stub_sibling)

        return snippet_root.get_simplified_dom_text()

    @time_execution_sync("--clickable_elements_to_string")
    def clickable_elements_to_string(
        self, include_attributes: list[str] | None = None
    ) -> str:
        """Convert the processed DOM content to HTML."""
        formatted_text = []

        def process_node(node: DOMBaseNode, depth: int) -> None:
            next_depth = int(depth)
            depth_str = depth * "\t"

            if isinstance(node, DOMElementNode):
                # Add element with highlight_index
                if node.highlight_index is not None:
                    next_depth += 1

                    text = node.get_all_text_till_next_clickable_element()
                    attributes_html_str = ""
                    if include_attributes:
                        attributes_to_include = {
                            key: str(value)
                            for key, value in node.attributes.items()
                            if key in include_attributes
                        }

                        # Easy LLM optimizations
                        # if tag == role attribute, don't include it
                        if node.tag_name == attributes_to_include.get("role"):
                            del attributes_to_include["role"]

                        # if aria-label == text of the node, don't include it
                        if (
                            attributes_to_include.get("aria-label")
                            and attributes_to_include.get("aria-label", "").strip()
                            == text.strip()
                        ):
                            del attributes_to_include["aria-label"]

                        # if placeholder == text of the node, don't include it
                        if (
                            attributes_to_include.get("placeholder")
                            and attributes_to_include.get("placeholder", "").strip()
                            == text.strip()
                        ):
                            del attributes_to_include["placeholder"]

                        if attributes_to_include:
                            # Format as key1='value1' key2='value2'
                            attributes_html_str = " ".join(
                                f"{key}='{value}'"
                                for key, value in attributes_to_include.items()
                            )

                    # Build the line
                    if node.is_new:
                        highlight_indicator = f"*[{node.highlight_index}]*"
                    else:
                        highlight_indicator = f"[{node.highlight_index}]"

                    line = f"{depth_str}{highlight_indicator}<{node.tag_name}"

                    if attributes_html_str:
                        line += f" {attributes_html_str}"

                    if text:
                        # Add space before >text only if there were NO attributes added before
                        if not attributes_html_str:
                            line += " "
                        line += f">{text}"
                    # Add space before /> only if neither attributes NOR text were added
                    elif not attributes_html_str:
                        line += " "

                    line += " />"  # 1 token
                    formatted_text.append(line)

                # Process children regardless
                for child in node.children:
                    process_node(child, next_depth)

            elif isinstance(node, DOMTextNode):
                # Add text only if it doesn't have a highlighted parent
                if (
                    not node.has_parent_with_highlight_index()
                    and node.parent
                    and node.parent.is_visible
                    and node.parent.is_top_element
                ):  # and node.is_parent_top_element()
                    formatted_text.append(f"{depth_str}{node.text}")

        process_node(self, 0)
        return "\n".join(formatted_text)

    def get_file_upload_element(
        self, check_siblings: bool = True
    ) -> Optional["DOMElementNode"]:
        # Check if current element is a file input
        if self.tag_name == "input" and self.attributes.get("type") == "file":
            return self

        # Check children
        for child in self.children:
            if isinstance(child, DOMElementNode):
                result = child.get_file_upload_element(check_siblings=False)
                if result:
                    return result

        # Check siblings only for the initial call
        if check_siblings and self.parent:
            for sibling in self.parent.children:
                if sibling is not self and isinstance(sibling, DOMElementNode):
                    result = sibling.get_file_upload_element(check_siblings=False)
                    if result:
                        return result

        return None

    def get_description(self) -> str:
        """
        Gets the most meaningful description for the element based on a
        prioritized list of attributes, falling back to its text content.
        This method checks for descriptive attributes first, as they often
        provide the most explicit, human-readable label intended for
        accessibility and forms. If no such attributes are found, it
        concatenates the visible text within the element.
        Returns:
                A simple string describing the element's meaning.
        """
        # 1. Prioritize attributes that explicitly define an element's purpose.
        #    This order is chosen to get the most specific label first.
        prioritized_attributes = [
            "aria-label",
            "placeholder",
            "title",
            "alt",  # Very important for images within links/buttons
            # "name",  # Common for form inputs
        ]
        attribute = ""
        for attr in prioritized_attributes:
            if self.attributes.get(attr):
                # Return the first descriptive attribute found, stripped of whitespace.
                attribute = self.attributes[attr].strip()
                return attribute
            
        # 3. As a final fallback, if the element is truly empty of descriptive
        #    attributes and text, use its tag name.
        text = self.get_all_text_till_next_clickable_element().strip()
        
        if text:
            text = " ".join(text.split()[:3])
        
        return text

SelectorMap = dict[int, DOMElementNode]


@dataclass
class DOMState:
    element_tree: DOMElementNode
    selector_map: SelectorMap
