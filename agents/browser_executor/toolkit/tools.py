import asyncio
from typing import Any, Annotated
from pydantic import BaseModel, Field
from typing import Literal
from langchain_core.tools import InjectedToolArg
import logging
from browser_use.context import BrowserContext
from typing import TYPE_CHECKING
from .registry import tool_registry  # Import from the registry in the same directory
from .utils import get_extraction_plan
from readability import Document
from google import genai

logger = logging.getLogger(__name__)


class ActionResult(BaseModel):
    message: str | None = None
    error: str | None = None
    data: Any = None

    def to_dict(self):
        return self.model_dump(exclude_none=True)


@tool_registry.register(
    is_active=lambda ctx: False
    and (ctx.domain in ["about:blank", "www.google.com"] or ctx.step == 0)
)
async def google_search(
    query: str,
    browser_context: Annotated[BrowserContext | None, InjectedToolArg] = None,
) -> ActionResult:
    # TODO: add the description to use it this as the grounding technique.
    """Searches on google"""
    try:
        await browser_context.navigate_to(f"https://www.google.com/search?q={query}")
        return ActionResult(message=f"Searched the query: {query}")
    except Exception as e:
        return ActionResult(message=f"Search failed: {str(e)}")


# TODO: we can always navigate the url in the new tab, eliminating the need of create_tab tool.
# @tool_registry.register()
async def goto_to_url(
    url: str, browser_context: Annotated[BrowserContext | None, InjectedToolArg] = None
) -> ActionResult:
    """Navigates the browser to a specific URL endpoint as a direct web address e.g. www.linkedin.com/jobs"""
    try:
        if not url.startswith("http://") and not url.startswith("https://"):
            url = f"https://{url}"
        await browser_context.navigate_to(url)
        return ActionResult(message=f"Navigated to {url}")

    except Exception as e:
        return ActionResult(error=f"Failed to navigate to {url}. {str(e)}")


@tool_registry.register()
async def click_element(
    element_index: int,
    browser_context: Annotated[BrowserContext | None, InjectedToolArg] = None,
) -> ActionResult:
    """Clicks an interactive element, such as a button or link, identified by its numbered label."""

    try:
        element_node = await browser_context.get_dom_element_by_index(element_index)

        if not element_node:
            logger.debug(f"Element with index {element_index} not found.")
            return ActionResult(error=f"Element index {element_index} not found.")

        session = await browser_context.get_session()
        initial_pages = len(session.context.pages)

        # if element has file uploader then dont click
        # if await browser_context.is_file_uploader(element_node):
        #     return ActionResult(message=f'Index {element_index} - has an element which opens file upload dialog. To upload files please use a specific function to upload files ')

        download_path = await browser_context._click_element_node(element_node)
        if download_path:
            message = f"Downloaded file to {download_path}"
        else:
            # FIXME: Instead of returning the element_node we can find the lastest handle present using xpath, providing the LLM the feedback.
            message = f"Clicked at '{element_node.get_description()}' with index [{element_index}]"

        session = await browser_context.get_session()
        if len(session.context.pages) > initial_pages:
            new_tab_msg = "New tab opened"
            message += f" - {new_tab_msg}"
            await browser_context.switch_to_tab(-1)

        return ActionResult(message=message)

    except Exception as e:
        logger.error(f"Click failed : {str(e)}")
        return ActionResult(
            error=f"Failed to click element index {element_index}, most likely the state has changed."
        )


# FIXME: handle overriding the current text.
@tool_registry.register()
async def type_text(
    element_index: int,
    text: str,
    press_enter: bool,
    browser_context: Annotated[BrowserContext | None, InjectedToolArg] = None,
) -> ActionResult:
    """Types text directly into a textfield, identified by its numbered label."""

    element_node = await browser_context.get_dom_element_by_index(element_index)

    if not element_node:
        return ActionResult(error=f"Element index {element_index} not found")

    try:
        element_description = element_node.get_description()

        # TODO: add more checks.
        if (
            element_node.tag_name == "button"
            or element_node.attributes.get("role") == "button"
        ):
            return ActionResult(
                error=f"Element {element_index}({element_description}) is a button"
            )

        await browser_context._input_text_element_node(element_node, text)
        message = f"Typed text in element {element_index}({element_description})"
        # FIXME: implement press_keys in browser_context and handle the stale state if type text fails.
        if press_enter:
            page = await browser_context.get_agent_current_page()
            await page.keyboard.press("Enter")
            message += " and sent it by pressing Enter key"

        return ActionResult(message=message)

    except Exception as e:
        logger.error(f"Failed to type text into element {element_index}: {str(e)}")
        return ActionResult(
            error=f"Failed to type text into element {element_index}({element_node.get_description()})"
        )


# FIXME: we can reduce the wait tool request in case of content loading, based on the no. interative element present - in context.py
@tool_registry.register()
async def wait(
    seconds: int,
    browser_context: Annotated[BrowserContext | None, InjectedToolArg] = None,
) -> ActionResult:
    """Pauses execution. Use it to wait for content loading and user required actions or interactions."""
    await asyncio.sleep(seconds)
    return ActionResult(message=f"Waited for {seconds} seconds")


# @tool_registry.register()
async def scroll(
    amount: int = 600,
    element_index: int | None = None,
    browser_context: Annotated[BrowserContext | None, InjectedToolArg] = None,
) -> ActionResult:
    """Scrolls the main page or a specific section. To scroll a particular section, dialog, or overlay, an element index within that area must be provided."""

    try:
        page = await browser_context.get_current_page()

        if element_index > -1:
            # --- Scroll a specific element ---
            element = await browser_context.get_dom_element_by_index(element_index)
            if not element:
                return ActionResult(
                    error=f"Element with index {element_index} not found."
                )

            bbox = element.bbox
            if not bbox:
                return ActionResult(
                    error=f"Could not get the bounding box for element {element_index}."
                )

            # Position the mouse over the center of the element
            x = bbox["x"] + bbox["width"] / 2
            y = bbox["y"] + bbox["height"] / 2
            await page.mouse.move(x, y)

            await page.mouse.wheel(0, amount)

            target_info = f"element at index {element_index}"

        else:
            if page.viewport_size:
                viewport = page.viewport_size
            else:
                viewport = await page.evaluate(
                    "() => ({ width: window.innerWidth, height: window.innerHeight })"
                )

            x, y = viewport["width"] / 2, viewport["height"] / 2

            await page.mouse.move(x, y)
            await page.mouse.wheel(0, amount)
            target_info = "the main page"

        # FIXME: add a scroll simulation.
        scroll_direction = "down" if amount > 0 else "up"
        message = f"Successfully scrolled {target_info} {scroll_direction} by {abs(amount)} pixels."
        return ActionResult(message=message)

    except Exception as e:
        logger.debug(f"Scroll failed: {str(e)}")
        return ActionResult(message=f"Scroll failed: {str(e)}")


@tool_registry.register(
    is_active=lambda ctx: ctx.last_action in ["scroll"] and ctx.step > 0
)
async def find(
    name: str,
    role: str,
    tag: str,
    browser_context: Annotated[BrowserContext | None, InjectedToolArg] = None,
) -> ActionResult:
    """Finds and scrolls to a specific element or text on the page. Provide semantic attributes like name, role, and tag for the most precise search."""

    try:
        page = await browser_context.get_agent_current_page()

        # --- Attempt #1: The "Perfect Match" (Highest Precision) ---
        locator = None
        count = 0

        if name and role and tag:
            locator = page.locator(f"{tag}").filter(
                has=page.get_by_role(role, name=name, exact=False)
            )
            count = await locator.count()

        if count == 0 and name and role:
            locator = page.get_by_role(role, name=name, exact=False)
            count = await locator.count()

        if count == 0 and name and tag:
            locator = page.locator(f"{tag}:text-matches('{name}', 'i')")
            count = await locator.count()

        if count == 1:
            element = locator.first
            await element.evaluate("el => el.scrollIntoView({block: 'start'})")
            await page.wait_for_load_state("domcontentloaded", timeout=5000)
            return ActionResult(
                message=f"Successfully found and scrolled to element: '{name}'"
            )

        # --- Attempt #2: The "Simple Text Fallback" ---
        print(
            "Precise match failed or was not possible. Falling back to simple text search."
        )
        locator = page.get_by_text(name, exact=False)

        count = await locator.count()
        if count == 1:
            element = locator.first
            # Scrolling the element at the very start.
            await element.evaluate("el => el.scrollIntoView({block: 'start'})")
            await page.wait_for_load_state("domcontentloaded", timeout=5000)
            return ActionResult(
                message=f"Successfully found and scrolled to element: '{name}'"
            )

        elements = []
        for i in range(count):
            element = locator.nth(i)
            element_info = {
                "index": i,
                "text": await element.inner_text(),
                "tag": await element.evaluate(
                    "(element) => element.tagName.toLowerCase()"
                ),
                "role": await element.evaluate(
                    '(element) => element.getAttribute("role")'
                )
                or "none",
            }
            elements.append(element_info)

        # FIXME: --- Step 3: Handle Ambiguity Using LLM. ---
        return ActionResult(
            message=f"Found multiple ({len(elements)}) elements matching '{name}'. Disambiguation is required.",
            data=elements,
        )

    except Exception as e:
        logger.error(f"Failed to execute find tool: {str(e)}")
        return ActionResult(
            error=f"An unexpected error occurred while trying to find the element: {str(e)}"
        )


@tool_registry.register(is_active=lambda ctx: ctx.step > 0)
async def extract(
    query: str,
    element_index: int | None = None,
    browser_context: Annotated[BrowserContext | None, InjectedToolArg] = None,
) -> ActionResult:
    """Extracts content of the viewport or complete page when a manual reading is complex. Use it to get the full text of an article, extract structured data like tables, lists, images etc.
    query: A clear, natural language description of the information you need. e.g. 'the main content of the article', 'a list of all user comments', 'the financial data table'
    element_index: Use to extract a single item directly, or provide as an example to extract a list of similar items (if available in browser state)
    """

    try:
        page = await browser_context.get_agent_current_page()

        goal = None
        selector = None

        import re

        main_content_pattern = re.compile(
            r"\b(main|article|body|content|post|text)\b", re.IGNORECASE
        )

        if main_content_pattern.search(query) and element_index is None:
            goal = "MAIN_CONTENT"

        elif element_index is not None:
            logger.info(
                f"Executing extract in 'element' mode for index {element_index}"
            )
            element = await browser_context.get_dom_element_by_index(element_index)

            if not element:
                return ActionResult(
                    error=f"Element with index {element_index} not found."
                )

            contextual_snippet = element.get_contextual_dom_text()
            print(
                f"Contextual DOM Snippet: size: {len(contextual_snippet)} \n {contextual_snippet}"
            )

            plan = await get_extraction_plan(
                query=query,
                dom=contextual_snippet,
                element_index=element_index,
                element_description=element.get_description(),
            )
            print(f"Generated extraction plan: {plan}")

            goal = plan.goal
            selector = plan.selector

        else:
            logger.info(f"Executing extract in 'discovery' mode for query: '{query}'")

            simplified_dom = (
                browser_context.current_state.element_tree.get_simplified_dom_text()
            )
            print(f"Simplified DOM with len: {len(simplified_dom)}")

            # FIXME: use the user provided goal also to generate more accurate extraction plans.
            plan = await get_extraction_plan(query=query, dom=simplified_dom)
            print(f"Generated extraction plan: {plan}")

            goal = plan.goal
            selector = plan.selector

        try:
            if goal == "MAIN_CONTENT":
                print("Extracting main content using readability...")
                html_content = await page.content()
                doc = Document(html_content)
                main_content_html = doc.summary(html_partial=True)
                print(f"Extracted main content for article: '{len(main_content_html)}'")
                return ActionResult(
                    message=f"Extracted main content for article: '{doc.title()}'",
                    data=main_content_html,
                )

            if not selector:
                return ActionResult(
                    error=f"The extraction strategist failed to provide a selector for the goal '{goal}'."
                )

            elements = page.locator(selector)
            count = await elements.count()
            if count == 0:
                print(f"No elements found for selector: {selector}")
                return ActionResult(
                    message=f"The generated selector '{selector}' did not find any elements."
                )

            if goal == "SINGLE_ITEM":
                print(f"Extracting single item for query: '{query}'")
                data = await elements.first.inner_text()
                print(f"Extracted text for query: '{data}'")
                return ActionResult(
                    message=f"Extracted text for query: '{query}'", data=data
                )

            elif goal == "LIST_OF_ITEMS":
                print(f"Extracting list of items for query: '{query}'")
                data = await elements.all_inner_texts()
                print(
                    f"Extracted {len(data)} items for query: '{query}', Data: \n{data}..."
                )  # Print first 10 items for debugging
                return ActionResult(
                    message=f"Extracted {len(data)} items for query: '{query}'",
                    data=data,
                )

            # elif goal == "TABLE":
            #     table_data = await _extract_table_data(elements.first)
            #     return ActionResult(message=f"Extracted table with {len(table_data)} rows.", data=table_data)

            else:
                return ActionResult(
                    error=f"Unknown goal '{goal}' returned by strategist."
                )
        except Exception as e:
            logger.error(f"Failed to execute extract tool: {str(e)}")
            return ActionResult(
                error=f"An unexpected error occurred during extraction: {str(e)}"
            )

    except Exception as e:
        logger.error(f"Failed to execute extract tool: {str(e)}")
        return ActionResult(
            error=f"An unexpected error occurred during extraction: {str(e)}"
        )


@tool_registry.register()
async def finish_task(
    reason: Literal["TASK_COMPLETED", "TASK_FAILED"],
    description: str,
    browser_context: Annotated[BrowserContext | None, InjectedToolArg] = None,
) -> ActionResult:
    """Finishes the running task."""

    if reason not in ["TASK_COMPLETED", "TASK_FAILED"]:
        return ActionResult(
            error=f"Invalid reason: {reason}. Must be 'TASK_COMPLETED' or 'TASK_FAILED'."
        )

    return ActionResult(message=f"{reason} because {description}")


@tool_registry.register(is_active=lambda ctx: ctx.text_field_focused)
async def press_keys(
    keys: str, browser: Annotated[BrowserContext | None, InjectedToolArg] = None
) -> ActionResult:
    """Simulates key press or keyboard shortcuts. e.g. 'Enter', 'Control+A' etc."""
    try:
        page = await browser.get_agent_current_page()
        await page.keyboard.press(keys)
        return ActionResult(message=f"Pressed keys: {keys}")
    except Exception as e:
        return ActionResult(error=f"Failed to press keys '{keys}': {str(e)}")


# FIXME: write js script to send feedback if section is not further scrollable.
@tool_registry.register()
async def scroll(
    bounding_box: list[int],
    direction: str,
    scroll_area: str,
    browser_context: Annotated[BrowserContext, InjectedToolArg] = None,
) -> ActionResult:
    """Scrolls within a specific area defined by a bounding box.
    Use this for scrollable non-labeled area/section of the page.
    The bounding_box should be [ymin, xmin, ymax, xmax] normalized to 0-1000"""

    try:
        # Get the current page and verify it exists
        page = await browser_context.get_agent_current_page()
        if not page:
            return ActionResult(error="No active page found")

        if page.viewport_size:
            viewport = page.viewport_size
        else:
            viewport = await page.evaluate(
                "() => ({ width: window.innerWidth, height: window.innerHeight })"
            )

        if not viewport:
            return ActionResult(error="Could not determine viewport size")

        height, width = viewport.get("height"), viewport.get("width")

        ymin, xmin, ymax, xmax = bounding_box

        # Calculate target coordinates
        y = ((ymin + ymax) / 2) / 1000 * height
        x = ((xmin + xmax) / 2) / 1000 * width

        # Move mouse to target area
        asyncio.create_task(
            browser_context.animator.scroll(
                direction,
                coords={"x": x, "y": y},
                text="Scrolling using spatial understanding",
            )
        )
        await page.mouse.move(x, y)

        amount = 700
        scroll_delta_y = amount if direction == "down" else -amount

        # Use page from the browser_context for wheel action
        await page.mouse.wheel(0, scroll_delta_y)
        await page.wait_for_timeout(500)

        return ActionResult(
            message=f"Scrolled {scroll_area} by {amount} pixels {direction}wards"
        )
    except Exception as e:
        logger.error(f"Error scrolling: {e}")
        return ActionResult(error=f"Failed to scroll")


@tool_registry.register()
async def navigate(
    action: Literal["goto", "back", "forward", "refresh"],
    url: str | None = None,
    browser_context: Annotated[BrowserContext | None, InjectedToolArg] = None,
) -> ActionResult:
    """Handles all browser navigation like going to a URL, reloading, or moving in history. url: The URL to navigate to (only required for the 'goto' action)."""
    if not browser_context:
        return ActionResult(error="Browser context is not available.")

    try:
        page = await browser_context.get_agent_current_page()

        if action == "goto":
            if not url:
                return ActionResult(error="A 'url' is required for the 'goto' action.")
            await page.goto(url)
            await page.wait_for_load_state()
            return ActionResult(message=f"Navigated to URL: {url}")

        elif action == "back":
            await page.go_back()
            await page.wait_for_load_state()
            return ActionResult(message="Navigated back in history.")

        elif action == "forward":
            await page.go_forward()
            await page.wait_for_load_state()
            return ActionResult(message="Navigated forward in history.")

        elif action == "refresh":
            await page.reload()
            await page.wait_for_load_state()
            return ActionResult(message="Page has been refreshed.")

        else:
            return ActionResult(
                error=f"Invalid action '{action}'. Must be one of 'goto', 'back', 'forward', or 'refresh'."
            )

    except Exception as e:
        # Generic error handler for unexpected issues
        return ActionResult(
            error=f"Failed to perform navigation action '{action}': {str(e)}"
        )












