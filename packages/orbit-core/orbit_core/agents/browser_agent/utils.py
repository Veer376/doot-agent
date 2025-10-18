import os
import logging
from PIL import Image, ImageDraw, ImageFont
from orbit_core.utils.logging_utils import get_agent_logger
from .messages.error_messages import MessageException
from PIL import Image
import functools
import logging
import traceback
import asyncio
import base64

logger = logging.getLogger(__name__)


def error_handler(func):
    log = logging.getLogger(func.__qualname__)

    def wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except Exception as e:
            log.error(f"Error: {e}")
            raise
    return wrapper


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


def escalate_error(func):
    logger = get_agent_logger(f"{func.__name__}")
    
    if asyncio.iscoroutinefunction(func):
        @functools.wraps(func)
        async def wrapper(*args, **kwargs):
            try:
                return await func(*args, **kwargs)
            except MessageException as e:
                logger.info(f"Escalating MessageException {e.__class__.__name__} to LLM")
            except Exception as e:
                logger.error(f"{e}")
                logger.debug(traceback.format_exc())
        return wrapper
    
    else:
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            try:
                return func(*args, **kwargs)
            except MessageException as e:
                logger.info(f"Escalating MessageException: {str(e)} to LLM") 
            except Exception as e:
                logger.error(f"{e}")
                logger.debug(traceback.format_exc())
        return wrapper


def compress(image: str, quality: int = 10, convert_to_bw: bool = False) -> str:
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


class BBoxRenderer:
    """
    Class to handle highlighting elements on screenshots with bounding boxes and labels.
    Provides a configurable way to render visual indicators for interactive elements.
    """

    def __init__(
        self,
        box_border_width: int = 2,
        box_color: str = "#000000",
        label_font_color: str = "#FFFFFF",
        label_padding_x: int = 1,
        label_padding_y: int = 1,
        font_size: int = 20,
        font_family: str | None = None,
    ):
        """
        Initialize the ScreenshotHighlighter with customizable styling options.

        Args:
            box_border_width: Width of the bounding box border in pixels
            box_color: Color of the bounding box as hex string
            label_font_color: Color of the label text as hex string
            label_padding_x: Horizontal padding for labels in pixels
            label_padding_y: Vertical padding for labels in pixels
            font_size: Font size for labels in points
            font_family: Font family name to use (will fall back to default if not found)
        """
        # Box styling
        self.BOX_BORDER_WIDTH = box_border_width
        self.BOX_COLOR = box_color

        # Label styling
        self.LABEL_FONT_COLOR = label_font_color
        self.LABEL_PADDING_X = label_padding_x
        self.LABEL_PADDING_Y = label_padding_y
        self.FONT_SIZE = font_size
        self.FONT_FAMILY = font_family

        # Try to load the specified font, falling back to default if necessary
        self.font = self._load_font()
    
    
    def _load_font(self) -> ImageFont.ImageFont:
        """Load the font to use for labels, with fallbacks if the requested font isn't available."""
        try:
            # Try to use the specified font family if provided
            if self.FONT_FAMILY:
                # Try different methods to load the font
                try:
                    return ImageFont.truetype(self.FONT_FAMILY, size=self.FONT_SIZE)
                except (OSError, IOError):
                    pass

            # Try to load a default system font with our size
            try:
                return ImageFont.load_default(size=self.FONT_SIZE)
            except Exception:
                return ImageFont.load_default()

        except Exception:
            # Absolute fallback
            return ImageFont.load_default()

    def render_bboxes(
        self, base64_screenshot: str, selector_map: dict
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
        try:
            from browser_use.dom.types import BoundingBox
        except ImportError:
            BoundingBox = None

        if not selector_map:
            return base64_screenshot

        if not base64_screenshot:
            return ""

        try:
            import io
            # Convert base64 to PIL Image
            image_data = base64.b64decode(base64_screenshot)
            image = Image.open(io.BytesIO(image_data))
            draw = ImageDraw.Draw(image)
            img_width, img_height = image.size

            # List to track placed labels to avoid overlapping
            placed_labels = []

            # Default device pixel ratio
            device_pixel_ratio = 1.0

            # Create a font for the labels
            # In newer Pillow versions, we can use load_default with size
            font = None
            # Use the font that was loaded in __init__
            font = self.font
            
            # Process each bounding box and draw highlights
            for idx, element_node in selector_map.items():
                # Skip elements without bounding box information
                if not hasattr(element_node, "bbox") or not element_node.bbox:
                    continue

                # Get bounding box object
                bbox = element_node.bbox

                try:
                    if isinstance(bbox, dict):
                        # Dictionary access
                        x_pos = bbox.get("x", 0) or 0
                        y_pos = bbox.get("y", 0) or 0
                        width = bbox.get("width", 0) or 0
                        height = bbox.get("height", 0) or 0
                        viewport_width = (
                            bbox.get("viewport_width", img_width) or img_width
                        )
                        viewport_height = (
                            bbox.get("viewport_height", img_height) or img_height
                        )
                        device_pixel_ratio = bbox.get("device_pixel_ratio", 1.0) or 1.0
                        iframe_offset_x = bbox.get("iframe_offset_x", 0) or 0
                        iframe_offset_y = bbox.get("iframe_offset_y", 0) or 0
                        absolute_x = x_pos + iframe_offset_x
                        absolute_y = y_pos + iframe_offset_y
                    else:
                        # Object access for BoundingBox objects - now using __iter__ when needed
                        try:
                            # Direct attribute access
                            x_pos = getattr(bbox, "x", 0) or 0
                            y_pos = getattr(bbox, "y", 0) or 0
                            width = getattr(bbox, "width", 0) or 0
                            height = getattr(bbox, "height", 0) or 0
                            device_pixel_ratio = (
                                getattr(bbox, "device_pixel_ratio", 1.0) or 1.0
                            )

                            viewport_width = (
                                getattr(bbox, "viewport_width", img_width) or img_width
                            )
                            viewport_height = (
                                getattr(bbox, "viewport_height", img_height)
                                or img_height
                            )

                            iframe_offset_x = getattr(bbox, "iframe_offset_x", 0) or 0
                            iframe_offset_y = getattr(bbox, "iframe_offset_y", 0) or 0

                            # Get absolute coordinates
                            if hasattr(bbox, "absolute_x") and hasattr(
                                bbox, "absolute_y"
                            ):
                                absolute_x = bbox.absolute_x
                                absolute_y = bbox.absolute_y
                            else:
                                absolute_x = x_pos + iframe_offset_x
                                absolute_y = y_pos + iframe_offset_y
                        except Exception:
                            # Use our new __iter__ implementation (x, y, width, height)
                            x_pos, y_pos, width, height = bbox
                            viewport_width = img_width
                            viewport_height = img_height
                            device_pixel_ratio = 1.0
                            absolute_x = x_pos
                            absolute_y = y_pos
                except Exception:
                    # Skip if we can't extract coordinates
                    continue

                # Safety checks and scaling
                viewport_width = max(1, viewport_width)
                viewport_height = max(1, viewport_height)
                device_pixel_ratio = max(0.1, device_pixel_ratio)

                # Calculate scaling factors
                scale_x = float(img_width) / viewport_width
                scale_y = float(img_height) / viewport_height

                # Apply the scale factor to transform DOM coordinates to image coordinates
                x1 = int(absolute_x * scale_x)
                y1 = int(absolute_y * scale_y)
                x2 = int((absolute_x + width) * scale_x)
                y2 = int((absolute_y + height) * scale_y)

                # Safety check for coordinates
                x1 = max(0, x1)
                y1 = max(0, y1)
                x2 = min(img_width - 1, x2)
                y2 = min(img_height - 1, y2)

                # Skip drawing if the resulting box is too small or invalid
                if x2 <= x1 or y2 <= y1:
                    continue

                try:
                    # Create highlight box similar to JavaScript version
                    # Draw a plain rectangle with the specified border width
                    draw.rectangle(
                        [x1, y1, x2, y2],
                        outline=self.BOX_COLOR,  # Use black color for consistency with JS
                        width=self.BOX_BORDER_WIDTH,  # Use consistent border width
                    )

                    # Draw label - using the same positioning logic as JavaScript version
                    self._draw_label(
                        draw,
                        x1,
                        y1,
                        x2,
                        y2,
                        self.BOX_COLOR,  # Use black color for the label background
                        str(idx),
                        placed_labels,
                        img_width,
                        img_height,
                        self.font,  # Use the class's font attribute
                    )
                except Exception:
                    # If label drawing fails, just continue with the next element
                    continue

            # Convert back to base64 - ensure we're saving as RGB if needed
            output_buffer = io.BytesIO()

            # Convert RGBA to RGB if needed
            if image.mode == "RGBA":
                # Create a white background
                background = Image.new("RGB", image.size, (255, 255, 255))
                # Paste the image on the background (handles alpha)
                background.paste(image, mask=image.split()[3])
                # Save the result
                background.save(output_buffer, format="PNG", quality=100)
            else:
                # Save directly
                image.save(output_buffer, format="PNG", quality=100)

            output_buffer.seek(0)

            return base64.b64encode(output_buffer.getvalue()).decode("utf-8")

        except Exception as e:
            # Return the original screenshot if any error occurs
            return base64_screenshot

    def _draw_label(
        self,
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
        try:
            # Make sure we have a valid string label
            if not isinstance(label, str):
                label = str(label)

            # Safety check for coordinates and dimensions
            x1, y1, x2, y2 = float(x1), float(y1), float(x2), float(y2)
            img_width = max(1, int(img_width))
            img_height = max(1, int(img_height))

            # Determine text size based on our font
            try:
                # Try getbbox for most accurate text size (Pillow >=8.0.0)
                if hasattr(font, "getbbox"):
                    bbox = font.getbbox(label)
                    text_w, text_h = bbox[2] - bbox[0], bbox[3] - bbox[1]
                else:
                    # For older Pillow versions
                    text_w, text_h = font.getsize(label)

                # Apply a minimum size based on FONT_SIZE to ensure label visibility
                text_h = max(text_h, self.FONT_SIZE)
                text_w = max(text_w, self.FONT_SIZE * len(label) // 2)

            except (AttributeError, TypeError):
                # Fallback: estimate size based on our constant
                text_w = self.FONT_SIZE * len(label) // 2
                text_h = self.FONT_SIZE

            # Add padding as in JS: padding = "0px 1.5px 0px 1.2px"
            pad_x = self.LABEL_PADDING_X
            pad_y = self.LABEL_PADDING_Y
            label_width = text_w + (2 * pad_x)
            label_height = text_h + (2 * pad_y)
        except Exception:
            # Use minimal fallback values
            pad_x, pad_y = 2, 2
            label_width = 12 + (8 * len(label))
            label_height = 20

        # Following buildDomTree.js fallback logic for label placement
        # Check if bounding box is too small for the label
        is_too_narrow = (x2 - x1) <= 1.5 * label_width
        is_too_short = (y2 - y1) <= 1.5 * label_height

        chosen_rect = None

        # Default position - top-left corner (same as buildDomTree.js)
        if not is_too_narrow and not is_too_short:
            # Use the top-left corner
            label_x = x1
            label_y = y1

        # First fallback - place label to the left of the bounding box (like buildDomTree.js)
        elif (is_too_narrow or is_too_short) and x1 > label_width:
            # Check if we have space on the left side
            label_x = x1 - label_width + 1
            label_y = y1

            # Keep the label within image bounds
            if label_x < 0:
                # Not enough space on left, try above
                label_x = x1
                label_y = y1 - label_height

        # Second fallback - place above the box
        elif y1 > label_height:
            label_x = x1
            label_y = y1 - label_height

        # Last resort - place at top-left anyway (might overlap)
        else:
            label_x = x1
            label_y = y1

        # Clamp to image bounds
        label_x = max(0, min(label_x, img_width - label_width))
        label_y = max(0, min(label_y, img_height - label_height))

        # Create the label rectangle
        chosen_rect = (label_x, label_y, label_x + label_width, label_y + label_height)

        # Check for overlap with existing labels - if overlapping, adjust position
        while any(self._rects_overlap(chosen_rect, r) for r in placed_labels):
            # Try shifting it down slightly
            label_y += label_height // 2

            # If we're going off-screen, reset and try right side
            if label_y + label_height >= img_height:
                label_y = y1
                label_x = min(x2, img_width - label_width)  # Right side of box

                # If that still doesn't work, give up and accept the overlap
                if any(
                    self._rects_overlap(
                        (
                            label_x,
                            label_y,
                            label_x + label_width,
                            label_y + label_height,
                        ),
                        r,
                    )
                    for r in placed_labels
                ):
                    break

            # Update chosen rectangle
            chosen_rect = (
                label_x,
                label_y,
                label_x + label_width,
                label_y + label_height,
            )

        try:
            # Draw label background with black color
            # Match the JS version: background = "black", color = "white"
            draw.rectangle(chosen_rect, fill=self.BOX_COLOR)

            # Center text in label - match JS lineHeight and letterSpacing
            text_x = (chosen_rect[0] + chosen_rect[2]) / 2
            text_y = (chosen_rect[1] + chosen_rect[3]) / 2

            # Draw the text in white - matches JS: color = "white"
            try:
                # Try with anchor="mm" for middle centering (newer Pillow)
                draw.text(
                    (text_x, text_y),
                    label,
                    fill=self.LABEL_FONT_COLOR,
                    font=self.font,
                    anchor="mm",
                )

            except TypeError:
                # Fallback for older Pillow versions - approximate centering
                text_x = chosen_rect[0] + pad_x
                text_y = chosen_rect[1] + pad_y
                draw.text(
                    (text_x, text_y), label, fill=self.LABEL_FONT_COLOR, font=self.font
                )

            # Add to placed labels list
            placed_labels.append(chosen_rect)
        except Exception as e:
            # Simple fallback if drawing fails
            try:
                # Create a simple square indicator as last resort
                size = 16  # Small square
                simple_rect = (x1, y1, x1 + size, y1 + size)
                draw.rectangle(simple_rect, fill=self.BOX_COLOR)
                # Try to add the label text
                draw.text(
                    (x1 + size / 2, y1 + size / 2),
                    label,
                    fill=self.LABEL_FONT_COLOR,
                    font=self.font,
                    anchor="mm",
                )
            except:
                pass

    def _rects_overlap(self, r1: tuple, r2: tuple) -> bool:
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

