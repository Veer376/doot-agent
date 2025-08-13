import os
from dotenv import load_dotenv
from langchain.chat_models import init_chat_model
from enum import Enum
from langchain_core.tools import BaseTool, StructuredTool, Tool
import logging
from typing import Any, Callable, Dict, Literal, Optional, Type
from langchain_core.tools import tool
from langchain_core.messages import (
    AIMessage,
    HumanMessage,
    ToolMessage,
)
import base64
import io
from PIL import Image, ImageDraw, ImageFont

logger = logging.getLogger(__name__)


def save_to_file(path: str, filename: str, content: bytes | str, index: int = None):
    try:
        # Ensure directory exists
        os.makedirs(path, exist_ok=True)

        # Format the filename with index if provided
        if index is not None:
            base_name, ext = os.path.splitext(filename)
            final_filename = f"{base_name}_{index}{ext}"
        else:
            final_filename = filename

        # Create the full filepath
        filepath = os.path.join(path, final_filename)

        # Automatically determine the mode based on content type
        mode = "wb" if isinstance(content, bytes) else "w"
        encoding = (
            "utf-8" if mode == "w" else None
        )  # encode in case of string, and not bytes.
        with open(filepath, mode, encoding=encoding) as f:
            f.write(content)

        logger.debug(f"File saved to {filepath}")
        return filepath
    except Exception as e:
        logger.error(f"Failed to save file: {e}")
        raise


from PIL import Image


def compress_image(image: str, quality: int = 10, convert_to_bw: bool = False) -> str:
    """
    Compress a base64-encoded image and optionally convert it to black-and-white.

    Args:
        image: Image content as a base64-encoded string.
        quality: Compression quality (1-100, higher is better quality).
        convert_to_bw: Whether to convert the image to black-and-white.

    Returns:
        Compressed image content as a base64-encoded string, ready for API consumption.
    """
    try:
        import base64
        from io import BytesIO

        # Decode the base64 string to bytes
        # First check if the string contains the data URL prefix
        if "base64," in image:
            # Extract the base64 part after the comma
            image = image.split("base64,")[1]

        # Decode the base64 content to bytes
        image_bytes = base64.b64decode(image)

        # Open the image with PIL
        with Image.open(BytesIO(image_bytes)) as img:
            # Convert to black-and-white if specified
            if convert_to_bw:
                img = img.convert("L")

            # Save the image with compression to a BytesIO object
            output = BytesIO()
            img.save(
                output,
                format="JPEG",  # Always use JPEG for better compression
                optimize=True,
                quality=quality,
            )
            output.seek(0)

            # Convert back to base64 string
            compressed_bytes = output.read()
            compressed_base64 = base64.b64encode(compressed_bytes).decode("utf-8")

            logger.debug("Image compressed successfully")

            return compressed_base64

    except Exception as e:
        logger.error(f"Failed to compress image: {e}")
        raise


# def format_message(message):
#     """Pretty-print messages with a sleek terminal UI aesthetic."""

#     border = lambda label: f"\n╭─ {label} " + "─" * (68 - len(label)) + "\n"
#     close = "╰" + "─" * 70

#     if isinstance(message, AIMessage):
#         parts = [border("✨ AI")]

#         if getattr(message, "thought", None):
#             parts.append(f"│ 💭 Thinking   : {message.thought}")

#         if getattr(message, "content", None):
#             parts.append(f"│ 🏝️ Response   : {message.content}")

#         if getattr(message, "tool_calls", None):
#             parts.append("│ 🔧 Tool Calls :")
#             for call in message.tool_calls:
#                 name = call.get("name", "unknown_tool")
#                 args = call.get("args", {})
#                 arg_str = ", ".join(f"{k}='{v}'" for k, v in args.items())
#                 parts.append(f"│    └> {name}({arg_str})")

#         parts.append(close)
#         return "\n".join(parts)

#     elif isinstance(message, ToolMessage):
#         return (
#             border("⚙️ TOOL OUTPUT") +
#             f"│ {message.content}" +
#             "\n" + close
#         )

#     elif isinstance(message, HumanMessage):
#         return border("👤 HUMAN") + f"│ {message.content}" + "\n" + close

#     else:
#         return border(f"📦 {message.__class__.__name__.upper()}") + \
#                f"│ {getattr(message, 'content', '[No Content]')}" + "\n" + close

from rich.console import Console
from rich.panel import Panel
from rich.text import Text
from rich.markdown import Markdown
from langchain_core.messages import AIMessage, ToolMessage, HumanMessage

from rich.console import Console
from rich.panel import Panel
from rich.text import Text
from rich.padding import Padding
from rich.console import Group
from typing import Any

console = Console()
from rich.syntax import Syntax
from rich import box
from rich.markdown import Markdown

def print_message(message: Any, console: Console = None):
    """
    Formats and prints a message directly to the console using Rich,
    with automatic text wrapping and preserved indentation.
    """
    if console is None:
        console = Console()

    # --- Helper function to create consistently styled sections ---
    def _create_section(title: str, content: Any, indent: int = 3) -> Group:
        """Creates a title Text and a Padding-wrapped content Text or other renderable."""
        if not content:
            return Group()  # Return an empty group if there's no content

        # If content is already a rich renderable (like Syntax or Group), use it directly
        from rich.console import RenderableType

        if hasattr(content, "__rich__") or isinstance(content, RenderableType):
            content_element = content
        elif isinstance(content, str):
            # If it's a string, convert to Text as before
            if not content.strip():
                return Group()
            # content_element = Text(content.strip(), style="default")
            content_element = Markdown(content.strip())
        else:
            # For any other type, convert to string and then to Text
            content_element = Text(str(content).strip(), style="default")

        return Group(
            Text(title, style="bold"),
            Padding(content_element, (0, 0, 0, indent)),  # (top, right, bottom, left)
        )

    # --- Handlers for specific message types ---

    def _build_ai_panel(msg: Any) -> Panel:
        render_groups = []

        if getattr(msg, "thought", None):
            render_groups.append(_create_section("🤔 Thinking:", msg.thought))

        if getattr(msg, "content", None):
            render_groups.append(_create_section("💡 Reasoning:", msg.content))

        if getattr(msg, "tool_calls", None):
            from rich.console import Group as RichGroup

            # Create a separate section for each tool call
            tool_group = RichGroup()
            for call in msg.tool_calls:
                name = call.get("name", "unknown_tool")
                args_str = ", ".join(
                    f"{k}='{v}'" for k, v in call.get("args", {}).items()
                )
                code = f"> {name}({args_str})"
                syntax = Syntax(
                    code,
                    "python",
                    background_color="default",  # This removes the black bg
                    line_numbers=False,
                    word_wrap=True,
                    indent_guides=True,
                )
                tool_group.renderables.append(syntax)

            # Add the tool group directly to render_groups
            render_groups.append(_create_section("🔧 Tool Calls:", tool_group))

        # Filter out any empty groups before creating the final body
        body = Group(*[group for group in render_groups if group])
        title = Text(
            "✨ AI",
            style="bold green",
        )
        return Panel(
            body,
            title=title,
            title_align="right",
            border_style="bold green",
            expand=False,
            width=100,
            highlight=True,
            box=box.ROUNDED,
        )

    def _build_tool_panel(msg: Any) -> Panel:
        # Handle different possible structures of tool message content
        
        if isinstance(msg.content, dict):
            error = msg.content.get("error", None)
            message = msg.content.get("message", "")
        else:
            message = str(msg.content)
            error = None
            
        body = _create_section("Error" if error else "Success", error if error else message)
        title = Text("🔨 Tool", style="bold")
        return Panel(body, title=title, border_style="bold", expand=False, width=70)

    def _build_human_panel(msg: Any) -> Panel:
        body = _create_section("👤 User:", msg.content)
        title = Text("💬 Human Message", style="bold")
        return Panel(body, title=title, border_style="bold", expand=False, width=70)

    def _build_default_panel(msg: Any) -> Panel:
        body = _create_section("ℹ️ Message:", getattr(msg, "content", "[No Content]"))
        title = Text(f"📦 {msg.__class__.__name__}", style="bold")
        return Panel(body, title=title, border_style="magenta", expand=False, width=70)

    # --- Dispatcher to select the correct handler ---

    msg_type = message.__class__.__name__
    panel_builders = {
        "GeminiMessage": _build_ai_panel,
        "AIMessage": _build_ai_panel,
        "ToolMessage": _build_tool_panel,
        "HumanMessage": _build_human_panel,
    }

    builder = panel_builders.get(msg_type, _build_default_panel)
    panel_to_print = builder(message)

    console.print(panel_to_print)


def render_bboxes_on_screenshot(
    base64_screenshot: str, selector_map: dict = None
) -> str:
    """
    Draw bounding boxes on the screenshot for interactive elements in the selector_map.
    Each box will have a label in its top-right corner, with consistent color for box and label.
    Based on the ScreenshotHighlighter logic.

    Args:
        base64_screenshot: Base64 encoded screenshot image
        selector_map: Dictionary of element indices and their DOM nodes with bounding boxes

    Returns:
        Base64 encoded screenshot with bounding boxes
    """
    if not selector_map:
        return base64_screenshot

    try:
        # Print debug information about the selector map
        print(f"Drawing bounding boxes for {len(selector_map)} elements")
        elements_with_bbox = [
            idx for idx, elem in selector_map.items() if elem.bbox is not None
        ]
        print(f"  Elements with bounding box: {len(elements_with_bbox)}")

        # Define colors for each type of element (following ScreenshotHighlighter pattern)
        colors = {
            "L": "#0B9D68",  # Link-like
            "B": "#2B2BF7",  # Button-like
            "I": "#F68B30",  # Input-like
            "F": "#FF69B4",  # Form-like
            "O": "#4682B4",  # Option-like
            "M": "#F0554D",  # Menu-like
            # Default color for other elements:
            "D": "#808080",  # Default/Other
        }

        # Convert base64 to PIL Image
        image_data = base64.b64decode(base64_screenshot)
        image = Image.open(io.BytesIO(image_data))
        draw = ImageDraw.Draw(image)
        img_width, img_height = image.size

        # List to track placed labels to avoid overlapping
        placed_labels = []

        # Get device pixel ratio directly from the first element with bbox
        device_pixel_ratio = 1.0  # Default if not available

        # Check if any element has the device pixel ratio
        for idx in elements_with_bbox:
            element = selector_map[idx]
            if hasattr(element, "bbox") and element.bbox:
                if "device_pixel_ratio" in element.bbox:
                    device_pixel_ratio = element.bbox["device_pixel_ratio"]
                    break

        # Print diagnostic information
        print(f"  Image dimensions: {img_width}×{img_height}")
        print(f"  Device pixel ratio: {device_pixel_ratio}")
        print(f"  Number of elements with bbox: {len(elements_with_bbox)}")

        # Try to create a font - use default if specific font fails
        try:
            # Use a reasonable font size (14 if available)
            font = ImageFont.load_default(size=14)
        except Exception:
            # Fall back to basic default font
            font = ImageFont.load_default()

        # Process each bounding box and draw highlights
        for idx, element_node in selector_map.items():
            # Skip elements without bounding box information
            if not hasattr(element_node, "bbox") or not element_node.bbox:
                continue

            # Get bounding box coordinates
            bbox = element_node.bbox

            # Determine color key based on element type (first character of idx as a string)
            # Default to 'D' if idx isn't a string or is empty
            color_key = "D"
            if isinstance(idx, str) and idx:
                color_key = idx[0]

            # Use color from map, or fallback to default
            color = colors.get(color_key, colors["D"])

            # Get device pixel ratio from bbox if available, otherwise default to 1
            device_pixel_ratio = bbox.get("device_pixel_ratio", 1.0)

            # Calculate transformed coordinates accounting for device pixel ratio
            # Note: We're applying the device pixel ratio to convert CSS pixels to device pixels
            x1 = bbox["x"] * device_pixel_ratio
            y1 = bbox["y"] * device_pixel_ratio
            x2 = (bbox["x"] + bbox["width"]) * device_pixel_ratio
            y2 = (bbox["y"] + bbox["height"]) * device_pixel_ratio

            # Debug output for this specific element
            print(
                f"  Element {idx}: CSS pixels({bbox['x']},{bbox['y']},{bbox['width']},{bbox['height']})"
            )
            print(
                f"    Device ratio: {device_pixel_ratio}, Device pixels({x1:.1f},{y1:.1f},{x2-x1:.1f},{y2-y1:.1f})"
            )

            # Draw the box with increased width for visibility
            draw.rectangle([x1, y1, x2, y2], outline=color, width=3)

            # Draw label with proper positioning using the approach from ScreenshotHighlighter
            _draw_label(
                draw,
                x1,
                y1,
                x2,
                y2,
                color,
                str(idx),
                placed_labels,
                img_width,
                img_height,
                font,
            )

        # Convert back to base64
        output_buffer = io.BytesIO()
        image.save(output_buffer, format="PNG")  # Use PNG for best quality
        output_buffer.seek(0)

        # Log the size of the output image
        output_size = len(output_buffer.getvalue()) / 1024  # KB
        print(f"  Final image size: {output_size:.1f} KB")

        return base64.b64encode(output_buffer.getvalue()).decode("utf-8")

    except Exception as e:
        # Log the error
        print(f"Error drawing bounding boxes: {str(e)}")
        # Return the original screenshot if any error occurs
        return base64_screenshot


def _draw_label(
    draw: ImageDraw.ImageDraw,
    x1: float,
    y1: float,
    x2: float,
    y2: float,
    color: str,
    label: str,
    placed_labels: list,
    img_width: int,
    img_height: int,
    font: ImageFont.ImageFont,
):
    """
    Draw a label for a bounding box using smart positioning logic.
    Based on ScreenshotHighlighter._draw_label_scaled.

    Args:
        draw: ImageDraw object to draw on
        x1, y1, x2, y2: Bounding box coordinates
        color: Color to use for the label background
        label: Text to display in the label
        placed_labels: List of already placed labels to avoid overlap
        img_width, img_height: Dimensions of the image
        font: Font to use for the text
    """
    # Determine text size - use getbbox for accurate text size (Pillow >=8.0.0) or fallback
    try:
        bbox = font.getbbox(label)
        text_w, text_h = bbox[2] - bbox[0], bbox[3] - bbox[1]
    except (AttributeError, TypeError):
        # Fallback: estimate size
        text_w, text_h = 8 * len(label), 16

    # Add padding
    pad_x, pad_y = 4, 4
    label_width = text_w + (2 * pad_x)
    label_height = text_h + (2 * pad_y)

    # Generate candidate positions for label placement
    candidates = []

    # Above
    candidates.append((x1, y1 - label_height - 2))
    # Right
    candidates.append((x2 + 2, y1))
    # Below
    candidates.append((x1, y2 + 2))
    # Left
    candidates.append((x1 - label_width - 2, y1))
    # Inside top-right
    candidates.append((x2 - label_width - 2, y1 + 2))

    # Check each candidate position for overlap with existing labels
    chosen_rect = None
    for label_x, label_y in candidates:
        # Clamp to image bounds
        lx = max(0, min(label_x, img_width - label_width))
        ly = max(0, min(label_y, img_height - label_height))

        # Define the rectangle for this label
        rect = (lx, ly, lx + label_width, ly + label_height)

        # Check for overlap with existing labels
        if any(_rects_overlap(rect, r) for r in placed_labels):
            continue

        # Check if fully within image
        if rect[0] < 0 or rect[1] < 0 or rect[2] > img_width or rect[3] > img_height:
            continue

        chosen_rect = rect
        break

    # If no good position found, use a fallback position
    if chosen_rect is None:
        # Last resort - place inside image even if overlapping
        label_x = max(0, min(x2 - label_width - 2, img_width - label_width))
        label_y = max(0, min(y1 + 2, img_height - label_height))
        chosen_rect = (label_x, label_y, label_x + label_width, label_y + label_height)

    # Draw label background
    draw.rectangle(chosen_rect, fill=color)

    # Center text in label
    text_x = (chosen_rect[0] + chosen_rect[2]) / 2
    text_y = (chosen_rect[1] + chosen_rect[3]) / 2

    # Draw the text
    try:
        # Try with anchor="mm" for middle centering (newer Pillow)
        draw.text((text_x, text_y), label, fill="white", font=font, anchor="mm")
    except TypeError:
        # Fallback for older Pillow versions - approximate centering
        text_x = chosen_rect[0] + pad_x
        text_y = chosen_rect[1] + pad_y
        draw.text((text_x, text_y), label, fill="white", font=font)

    # Add to placed labels list
    placed_labels.append(chosen_rect)


def _rects_overlap(r1: tuple, r2: tuple) -> bool:
    """
    Check if two rectangles overlap.
    Each rectangle is defined as (x1, y1, x2, y2).
    """
    return not (
        r1[2] <= r2[0]  # r1 is left of r2
        or r1[0] >= r2[2]  # r1 is right of r2
        or r1[3] <= r2[1]  # r1 is above r2
        or r1[1] >= r2[3]  # r1 is below r2
    )


import functools
import logging
import traceback
import asyncio
logger = logging.getLogger("agent_error")

def error_handler(func):
    if asyncio.iscoroutinefunction(func):
        @functools.wraps(func)
        async def wrapper(*args, **kwargs):
            try:
                return await func(*args, **kwargs)
            except Exception as e:
                logger.error(f"Error in {func.__name__}: {e}")
                logger.debug(traceback.format_exc())
                # optionally: return fallback value or re-raise
        return wrapper
    else:
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            try:
                return func(*args, **kwargs)
            except Exception as e:
                logger.error(f"Error in {func.__name__}: {e}")
                logger.debug(traceback.format_exc())
        return wrapper
