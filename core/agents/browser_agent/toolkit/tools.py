import asyncio
import math
from typing import Any, Annotated, Literal, TYPE_CHECKING
from pydantic import BaseModel, Field
from langchain_core.tools import InjectedToolArg
from core.utils.logging_utils import get_toolkit_logger
from core.browser_use.context import BrowserContext
from .registry import tool_registry  # Import from the registry in the same directory
from .utils import get_extraction_plan
from readability import Document
from .types import ToolResult
from core.utils.logging_utils import BrowserLogger as Logger
import math
import asyncio
from typing import Annotated
from langgraph.runtime import get_runtime  # NOTE: consider using the get_runtime()
from langgraph.types import Command
from ..state import Snippet

logger = get_toolkit_logger("tools")
"""
Prompt:
since in the agent.py we are going to use the ToolNode() i wnat you to modify each meticuloulsy. 
1. Remove the browser_context and use the user_id from the InjectedToolArg("user_id") instead.
even though the browser_runtime doesn't accept the user_id and release the per user resource but 
this is how it gonna be. 
2. use the browser_runtime function to get the browser resource.
3. Now we don't have to return the ToolResult, we can directly return the str or list. (i don't know if dict will work)
4. for the directly changing the state, like tools updating the field reverse_tools, use the Command() and update the state directly, make sure to accept the InjectToolCallId in that case, update the state, and also include the final ToolMessage.
5. there is a concern, we have the ToolResult with error field, but in case of ToolNode how it will work,
a. if we left it and raise, the ToolNode will take it as error and will it fail the execution or transer it to the agent, if it fails then its good. because there is paramter handle_erros, so will be only ahndle the valuerror or all the errors, maybe we can configure that i guess.
b. we can handle it ourself, using ToolMessage but that will be tedious and we will lose the benefit of ToolNode(). first option needs to be digged in so that we can write the cleaner code.
so this 5. is something you must dig for. after digging let me know what you found and for now don't make any changes let just think about hte 5th point.

remove this prompt if you have complete making changes to the code.
"""

@tool_registry.register()
async def type_text(
    element_index: int,
    text: str,
    press_enter: bool,
    browser_context: Annotated[BrowserContext | None, InjectedToolArg] = None,
) -> ToolResult:
    """Types text into a focused text field or search and select the dropdown option, identified by its numbered label."""

    element_node = await browser_context.get_dom_element_by_index(element_index)

    if not element_node:
        logger.debug(f"Element index {element_index} not found", browser_context)
        return ToolResult(
            message=f"Element index {element_index} not found", status="error"
        )
        graph_id = None

    try:
        element_description = element_node.get_description()
        page = None

        if (
            element_node.tag_name == "button"
            or element_node.attributes.get("role") == "button"
        ):
            logger.warning(
                f"Element {element_index}({element_description}) is a button",
                browser_context,
            )
            return ToolResult(
                message=f"Element {element_index}({element_description}) is a button and cannot be typed into.",
                status="error",
            )

        dropdown_info = await browser_context.is_element_dropdown(element_node)

        if dropdown_info.get("is_dropdown"):
            logger.info(
                f"Element {element_index}({element_description}) is a dropdown.",
                browser_context,
            )
            asyncio.create_task(
                browser_context.animator.dropdown(
                    element_node, text="Getting dropdown options"
                )
            )

            try:
                page = await browser_context.get_agent_current_page()
                element_handle = await browser_context.get_locate_element(element_node)
                await element_handle.click(force=True)
                await asyncio.sleep(1)
                await page.keyboard.type(text, delay=100)
                await page.keyboard.press("Enter")
                await asyncio.sleep(1)
                dropdown_details = await browser_context.get_dropdown_details(
                    element_node
                )
                selected_options = dropdown_details.get("selected_options", [])
                asyncio.create_task(
                    browser_context.animator.dropdown(
                        element_node,
                        text=f"Selected options: '{", ".join(option.get("text") for option in selected_options)}'",
                    )
                )

                options = dropdown_details.get("options", [])
                message = (
                    f"ATTENTION: Element {element_index}({element_description}) is a dropdown menu. "
                    f"I've attempted to handle it by searching and selecting an option using keyboard input. "
                    "Please review the current selection against all available options below. "
                    "If you want to select another option, use the dropdown tool. "
                )
                return ToolResult(
                    message=message,
                    data={"selected_options": selected_options, "options": options},
                    reserve_tools=["select_dropdown_option"],
                )

            except Exception as e:
                logger.error(
                    f"Failed to interact with dropdown element {str(e)}",
                    browser_context,
                )
                return ToolResult(
                    message=f"Element {element_index}({element_description}) is dropdown element. Use the appropriate tool to interact with it."
                )

        await browser_context._input_text_element_node(element_node, text)
        message = f"Typed text in element {element_index}({element_description})"

        if press_enter:
            asyncio.create_task(browser_context.animator.key("Enter"))
            if page is None:
                page = await browser_context.get_agent_current_page()
            await page.keyboard.press("Enter")
            message += " and sent it by pressing Enter key"

        return ToolResult(message=message)

    except Exception as e:
        logger.error(
            f"Failed to type text into element {element_index}: {str(e)}",
            browser_context,
        )
        return ToolResult(
            error=f"Failed to type text into element {element_index}({element_node.get_description()})"
        )


@tool_registry.register(
    is_active=lambda ctx: False
    and (ctx.domain in ["about:blank", "www.google.com"] or ctx.step == 0)
)
async def google_search(
    query: str,
    browser_context: Annotated[BrowserContext | None, InjectedToolArg] = None,
) -> ToolResult:
    """Searches on google"""
    try:
        asyncio.create_task(browser_context.animator.processing(f"Searching '{query}'"))
        await browser_context.navigate_to(f"https://www.google.com/search?q={query}")
        return ToolResult(message=f"Searched the query: {query}")
    except Exception as e:
        logger.error(f"Google search failed: {str(e)}", browser_context)
        return ToolResult(message=f"Search failed: {str(e)}")


@tool_registry.register()
async def goto_url(
    url: str, browser_context: Annotated[BrowserContext | None, InjectedToolArg] = None
) -> ToolResult:
    """Navigates the browser to a specific URL endpoint as a direct web address e.g. www.linkedin.com/jobs"""
    try:
        if not url.startswith("http://") and not url.startswith("https://"):
            url = f"https://{url}"
        await browser_context.navigate_to(url)
        return ToolResult(message=f"Navigated to {url}")

    except Exception as e:
        logger.error(f"Failed to navigate to {url}: {str(e)}", browser_context)
        return ToolResult(
            message=f"Failed to navigate to {url}. {str(e)}", status="error"
        )


@tool_registry.register()
async def click_element(
    element_index: int,
    browser_context: Annotated[BrowserContext | None, InjectedToolArg] = None,
) -> ToolResult:
    """Clicks an interactive element, such as a dropdown or button, identified by its numbered label."""

    try:
        element_node = await browser_context.get_dom_element_by_index(element_index)

        if not element_node:
            logger.debug(
                f"Element with index {element_index} not found.", browser_context
            )
            return ToolResult(
                message=f"Element index {element_index} not found.", status="error"
            )

        session = await browser_context.get_session()
        initial_pages = len(session.context.pages)

        # if element has file uploader then dont click
        # if await browser_context.is_file_uploader(element_node):
        #     return ToolResult(message=f'Index {element_index} - has an element which opens file upload dialog. To upload files please use a specific function to upload files ')

        try:
            download_path = await browser_context._click_element_node(element_node)
            if download_path:
                message = f"Downloaded file to {download_path}"
            else:
                message = f"Clicked at element {element_index}({element_node.get_description()})"

        except Exception as click_error:
            logger.warning(
                f"Click encountered an error but may have succeeded: {str(click_error)}",
                browser_context,
            )
            message = f"Clicked at element {element_index}({element_node.get_description()}) - Note: Click succeeded but encountered post-click issues."

        session = await browser_context.get_session()
        if len(session.context.pages) > initial_pages:
            new_tab_msg = "New tab opened"
            message += f" - {new_tab_msg}"
            await browser_context.switch_to_tab(-1)

        else:
            try:
                dropdown_info = await browser_context.is_element_dropdown(element_node)
                if dropdown_info.get("is_dropdown", False):

                    # logger.info(
                    #     f"Element {element_index}({element_node.get_description()}) is a dropdown.",
                    #     browser_context,
                    # )
                    asyncio.create_task(
                        browser_context.animator.dropdown(
                            element_node, text="Getting dropdown options"
                        )
                    )

                    dropdown_details = await browser_context.get_dropdown_details(
                        element_node
                    )
                    message = (
                        f"BE AWARE: Element ({element_node.get_description()}) is also a dropdown. "
                        "If you think the dropdown options are not marked with numbered labels "
                        "or desired option is not visible, use select_dropdown_tool."
                    )
                    page = await browser_context.get_agent_current_page()
                    await page.keyboard.press("Escape")
                    return ToolResult(
                        message=message,
                        data={
                            "selected_options": dropdown_details.get(
                                "selected_options", []
                            ),
                            "options": dropdown_details.get("options", []),
                        },
                        reserve_tools=["select_dropdown_option"],
                    )

            except Exception as e:
                logger.error(
                    f"Failed to get dropdown details: {str(e)}", browser_context
                )

        return ToolResult(message=message)

    except Exception as e:
        logger.error(f"Click failed : {str(e)}", browser_context)
        return ToolResult(
            message=f"Failed to click element index {element_index}, most likely the state has changed.",
            status="error",
        )


@tool_registry.register()
async def wait(
    seconds: int,
    browser_context: Annotated[BrowserContext | None, InjectedToolArg] = None,
) -> ToolResult:
    """Pauses execution. Use it to wait for content loading and user required actions or interactions."""
    logger.info(f"Waiting for {seconds} seconds...", browser_context)
    await asyncio.sleep(seconds)
    return ToolResult(message=f"Waited for {seconds} seconds")


@tool_registry.register(
    is_active=lambda ctx: any(last_action in ["scroll"] for last_action in ctx.last_actions) and ctx.step > 0
)
async def find(
    text: str,
    role: str,
    tag: str,
    browser_context: Annotated[BrowserContext | None, InjectedToolArg] = None,
) -> ToolResult:
    """Finds and scrolls to a specific element or text on the page. Provide semantic attributes like text(name), role, and tag for the most precise search."""

    try:
        page = await browser_context.get_agent_current_page()

        # --- Attempt #1: The "Perfect Match" (Highest Precision) ---
        locator = None
        count = 0

        logger.info(
            f"Searching for '{text}' with role '{role}' and tag '{tag}'",
            browser_context,
        )
        asyncio.create_task(
            browser_context.animator.processing(
                f"Finding '{text}' with '{role}' and '{tag}'"
            )
        )

        if text and role and tag:
            locator = page.locator(f"{tag}").filter(
                has=page.get_by_role(role, name=text, exact=False)
            )
            count = await locator.count()

        if count == 0 and text and role:
            locator = page.get_by_role(role, name=text, exact=False)
            count = await locator.count()

        if count == 0 and text and tag:
            locator = page.locator(f"{tag}:text-matches('{text}', 'i')")
            count = await locator.count()

        if count == 1:
            element = locator.first
            await element.evaluate("el => el.scrollIntoView({block: 'start'})")
            await page.wait_for_load_state("domcontentloaded", timeout=5000)
            logger.info(f"Found and scrolled to element: '{text}'", browser_context)
            return ToolResult(
                message=f"Successfully found and scrolled to element: '{text}'"
            )

        # --- Attempt #2: The "Simple Text Fallback" ---
        logger.info(
            f"Precise match failed or was not possible. Falling back to simple text search.",
            browser_context,
        )
        locator = page.get_by_text(text, exact=False)

        count = await locator.count()
        if count == 1:
            element = locator.first
            # Scrolling the element at the very start.
            await element.evaluate("el => el.scrollIntoView({block: 'start'})")
            await page.wait_for_load_state("domcontentloaded", timeout=5000)

            logger.info(f"Found and scrolled to element: '{text}'", browser_context)
            return ToolResult(message=f"Found and scrolled to element: '{text}'")

        elements = []
        for i in range(count):
            element = locator.nth(i)
            # Generate a unique selector for the element
            tag = await element.evaluate("(element) => element.tagName.toLowerCase()")
            text = await element.inner_text()
            # A simple but often effective selector
            selector = f"{tag}:has-text('{text.strip()[:50]}')"

            element_info = {
                "index": i,
                "text": text,
                "tag": tag,
                "role": await element.evaluate(
                    '(element) => element.getAttribute("role")'
                )
                or "none",
                "selector": selector,
            }
            elements.append(element_info)

        logger.info(f"Found multiple elements matching '{text}'", browser_context)

        return ToolResult(
            message=f"Found multiple ({len(elements)}) elements matching '{text}'. Review the list and use the `find_by_selector` tool with the appropriate selector to proceed.",
            data=elements,
            reserve_tools=["find_by_selector"],
        )

    except Exception as e:
        logger.error(f"Failed to execute find tool: {str(e)}", browser_context)
        return ToolResult(
            error=f"An unexpected error occurred while trying to find the element: {str(e)}"
        )


@tool_registry.register(is_active=lambda ctx: ctx.step > 0)
async def extract(
    query: str,
    element_index: int | None = None,
    browser_context: Annotated[BrowserContext | None, InjectedToolArg] = None,
) -> ToolResult:
    """Extracts content of the viewport or complete page when a manual reading is complex. Use it to get the full text of an article, extract structured data like tables, lists, images etc.
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
                f"Executing extract in 'element' mode for index {element_index}",
                browser_context,
            )
            element = await browser_context.get_dom_element_by_index(element_index)

            if not element:
                logger.error(
                    f"Element with index {element_index} not found for extraction",
                    browser_context,
                )
                return ToolResult(
                    message=f"Element with index {element_index} not found.",
                    status="error",
                )

            contextual_snippet = element.get_contextual_dom_text()
            logger.debug(
                f"Contextual DOM Snippet: size: {len(contextual_snippet)}",
                browser_context,
            )

            plan = await get_extraction_plan(
                query=query,
                dom=contextual_snippet,
                element_index=element_index,
                element_description=element.get_description(),
            )
            logger.debug(f"Generated extraction plan: {plan}", browser_context)

            goal = plan.goal
            selector = plan.selector

        else:
            logger.info(
                f"Executing extract in 'discovery' mode for query: '{query}'",
                browser_context,
            )

            simplified_dom = (
                browser_context.current_state.element_tree.get_simplified_dom_text()
            )
            logger.debug(
                f"Simplified DOM with len: {len(simplified_dom)}", browser_context
            )

            # FIXME: use the user provided goal also to generate more accurate extraction plans.
            plan = await get_extraction_plan(query=query, dom=simplified_dom)
            logger.debug(f"Generated extraction plan: {plan}", browser_context)

            goal = plan.goal
            selector = plan.selector

        try:
            if goal == "MAIN_CONTENT":
                logger.info(
                    "Extracting main content using readability...", browser_context
                )
                html_content = await page.content()
                doc = Document(html_content)
                main_content_html = doc.summary(html_partial=True)
                logger.debug(
                    f"Extracted main content for article, length: {len(main_content_html)}",
                    browser_context,
                )
                return ToolResult(
                    message=f"Extracted main content for article: '{doc.title()}'",
                    data=main_content_html,
                )

            if not selector:
                return ToolResult(
                    message=f"The extraction strategist failed to provide a selector for the goal '{goal}'.",
                    status="error",
                )

            elements = page.locator(selector)
            count = await elements.count()
            if count == 0:
                logger.warning(
                    f"No elements found for selector: {selector}", browser_context
                )
                return ToolResult(
                    message=f"The generated selector '{selector}' did not find any elements."
                )

            if goal == "SINGLE_ITEM":
                logger.info(
                    f"Extracting single item for query: '{query}'", browser_context
                )
                data = await elements.first.inner_text()
                logger.debug(
                    f"Extracted text for query: '{query[:50]}...'", browser_context
                )
                return ToolResult(
                    message=f"Extracted text for query: '{query}'", data=data
                )

            elif goal == "LIST_OF_ITEMS":
                logger.info(
                    f"Extracting list of items for query: '{query}'", browser_context
                )
                data = await elements.all_inner_texts()
                logger.debug(
                    f"Extracted {len(data)} items for query: '{query}', Data: \n{data[:10]}...",
                    browser_context,
                )  # logger first 10 items for debugging
                return ToolResult(
                    message=f"Extracted {len(data)} items for query: '{query}'",
                    data=data,
                )

            # elif goal == "TABLE":
            #     table_data = await _extract_table_data(elements.first)
            #     return ToolResult(message=f"Extracted table with {len(table_data)} rows.", data=table_data)

            else:
                return ToolResult(
                    message=f"Unknown goal '{goal}' returned by strategist.",
                    status="error",
                )
        except Exception as e:
            logger.error(f"Failed to execute extract tool: {str(e)}", browser_context)
            return ToolResult(
                message=f"An unexpected error occurred during extraction: {str(e)}",
                status="error",
            )

    except Exception as e:
        logger.error(f"Failed to execute extract tool: {str(e)}", browser_context)
        return ToolResult(
            message=f"An unexpected error occurred during extraction: {str(e)}",
            status="error",
        )


@tool_registry.register()
async def finish_task(
    is_task_completed: bool,
    reason: str,
    browser_context: Annotated[BrowserContext | None, InjectedToolArg] = None,
) -> ToolResult:
    """Finishes the running task. Provide a reason that why you can't complete the task."""
    logger.info(
        f"Task {'Completed' if is_task_completed else 'Failed'}, reason: {reason}",
        browser_context,
    )
    # NOTE: use command to directly move to the task summarizer.
    return ToolResult(
        message=f"Task {'Completed' if is_task_completed else 'Failed'} because {reason}"
    )


async def press_keys(
    keys: str, browser_context: Annotated[BrowserContext | None, InjectedToolArg] = None
) -> ToolResult:
    """Simulates key press or keyboard shortcuts. e.g. 'Enter', 'Control+A' etc."""
    try:
        asyncio.create_task(browser_context.animator.key(keys))
        page = await browser_context.get_agent_current_page()
        await page.keyboard.press(keys)
        return ToolResult(message=f"Pressed keys: {keys}")
    except Exception as e:
        logger.error(f"Failed to press keys '{keys}': {str(e)}", browser_context)
        return ToolResult(
            message=f"Failed to press keys '{keys}': {str(e)}", status="error"
        )


@tool_registry.register()
async def scroll(
    bounding_box: list[int],
    scroll_pixels: int,
    direction: str,
    scroll_area_label: str,
    browser_context: Annotated[BrowserContext | None, InjectedToolArg] = None,
) -> ToolResult:
    """
    Scrolls within a specific area defined by a bounding box.
    Use for scrollable non-labeled areas/sections of the page.

    bounding_box: [ymin, xmin, ymax, xmax] normalized to 0-1000
    scroll_pixels: positive integer number of pixels to attempt to scroll
    direction: oneOf ["up", "down", "left", "right"]
    scroll_area_label: human-readable identifier of scroll target. e.g. "full page", "job section", "list of items in cart"
    """
    try:
        # --- Basic sanity checks & get page ---
        page = await browser_context.get_agent_current_page()

        if not page:
            return ToolResult(message="No active page found", status="error")

        direction = (direction or "").lower()
        if direction not in ("up", "down", "left", "right"):
            return ToolResult(
                message="direction must be one of 'up', 'down', 'left', 'right'",
                status="error",
            )

        ymin, xmin, ymax, xmax = bounding_box

        # --- Determine viewport size (width,height) ---
        if page.viewport_size:
            viewport = page.viewport_size
            width = viewport.get("width")
            height = viewport.get("height")
        else:
            viewport = await page.evaluate(
                "() => ({ width: window.innerWidth, height: window.innerHeight })"
            )
            width = viewport.get("width")
            height = viewport.get("height")

        if not (
            isinstance(width, (int, float))
            and isinstance(height, (int, float))
            and width > 0
            and height > 0
        ):
            logger.error("Could not determine viewport size", browser_context)
            return ToolResult(
                message="Could not determine viewport size", status="error"
            )

        # --- Compute central point in page viewport coordinates ---
        try:
            center_x = ((xmin + xmax) / 2.0) / 1000.0 * width
            center_y = ((ymin + ymax) / 2.0) / 1000.0 * height
        except Exception as e:
            logger.error(f"Error calculating coordinates: {e}", browser_context)
            return ToolResult(
                message=f"Error calculating scroll coordinates: {e}", status="error"
            )

        # Validate finite & inside viewport
        if not (math.isfinite(center_x) and math.isfinite(center_y)):
            logger.error(
                f"Invalid coordinates calculated: x={center_x}, y={center_y}",
                browser_context,
            )
            return ToolResult(
                message="Invalid scroll coordinates (not finite)", status="error"
            )

        if not (0 <= center_x < width and 0 <= center_y < height):
            logger.error(
                f"Coordinates out of viewport: x={center_x}, y={center_y}, width={width}, height={height}",
                browser_context,
            )
            return ToolResult(
                message="Computed scroll coordinates are outside the viewport",
                status="error",
            )

        # --- Prepare scroll deltas ---
        dx = 0
        dy = 0
        if direction == "down":
            dy = abs(int(scroll_pixels))
        elif direction == "up":
            dy = -abs(int(scroll_pixels))
        elif direction == "right":
            dx = abs(int(scroll_pixels))
        elif direction == "left":
            dx = -abs(int(scroll_pixels))

        try:
            asyncio.create_task(
                browser_context.animator.scroll(
                    direction,
                    coords={"x": center_x, "y": center_y},
                    text=f"Scroll: {scroll_area_label}",
                )
            )
        except Exception:
            # animator failure should not stop the scroll
            pass

        # --- Single evaluate that finds element, performs scroll and returns structured result ---
        js_result = await page.evaluate(
            """(params) => {
                const {x, y, dx, dy} = params
                // run as async to allow small timeout after scroll
                return (async () => {
                    function isFiniteNumber(n){ return typeof n === 'number' && isFinite(n); }
                    if (!isFiniteNumber(x) || !isFiniteNumber(y) || x < 0 || y < 0) {
                        return { error: 'invalid-coordinates' };
                    }

                    // Find topmost element at the viewport coordinates
                    let el = document.elementFromPoint(x, y);

                    // Helper to check overflow-scrollability
                    function isOverflowScrollable(node) {
                        try {
                            const style = window.getComputedStyle(node);
                            const overflowY = style.overflowY || style.overflow;
                            const overflowX = style.overflowX || style.overflow;
                            const yOk = /auto|scroll|overlay/.test(overflowY);
                            const xOk = /auto|scroll|overlay/.test(overflowX);
                            return { yOk, xOk };
                        } catch (e) {
                            return { yOk: false, xOk: false };
                        }
                    }

                    // Walk up to find the first scrollable container for the requested axis
                    let scrollEl = null;
                    let axis = (Math.abs(dy) > 0) ? 'y' : 'x';
                    let current = el;
                    while (current) {
                        if (current === document.body || current === document.documentElement) break;
                        const overflow = isOverflowScrollable(current);
                        if (axis === 'y') {
                            if (current.scrollHeight > current.clientHeight && overflow.yOk) {
                                scrollEl = current;
                                break;
                            }
                        } else {
                            if (current.scrollWidth > current.clientWidth && overflow.xOk) {
                                scrollEl = current;
                                break;
                            }
                        }
                        current = current.parentElement;
                    }

                    // If none found, fallback to document.scrollingElement (or html)
                    if (!scrollEl) {
                        scrollEl = document.scrollingElement || document.documentElement || document.body;
                    }

                    // Collect before state
                    const beforeTop = scrollEl.scrollTop;
                    const beforeLeft = scrollEl.scrollLeft;
                    const maxScrollY = Math.max(0, (scrollEl.scrollHeight || document.documentElement.scrollHeight) - (scrollEl.clientHeight || window.innerHeight));
                    const maxScrollX = Math.max(0, (scrollEl.scrollWidth || document.documentElement.scrollWidth) - (scrollEl.clientWidth || window.innerWidth));

                    // Perform scroll
                    try {
                        // Use scrollBy to precisely target the element
                        scrollEl.scrollBy({ left: dx, top: dy, behavior: 'auto' });
                    } catch (e) {
                        // If the chosen element doesn't accept scrollBy, try window fallback
                        try {
                            window.scrollBy({ left: dx, top: dy, behavior: 'auto' });
                            scrollEl = document.scrollingElement || document.documentElement || document.body;
                        } catch (e2) {
                            // give up
                        }
                    }

                    // Wait briefly for layout / paint
                    await new Promise((r) => setTimeout(r, 60));

                    // Collect after state
                    const afterTop = scrollEl.scrollTop;
                    const afterLeft = scrollEl.scrollLeft;
                    const scrolledY = Math.abs(afterTop - beforeTop);
                    const scrolledX = Math.abs(afterLeft - beforeLeft);

                    // Build elementInfo descriptor (safe for JSON)
                    let elementInfo = null;
                    try {
                        elementInfo = {
                            tag: (scrollEl.tagName || '').toLowerCase(),
                            id: scrollEl.id || null,
                            class: scrollEl.className ? String(scrollEl.className) : null
                        };
                    } catch (e) {
                        elementInfo = { tag: 'unknown', id: null, class: null };
                    }

                    return {
                        error: null,
                        elementInfo,
                        axis,
                        before: { top: beforeTop, left: beforeLeft },
                        after: { top: afterTop, left: afterLeft },
                        scrolled: { y: scrolledY, x: scrolledX },
                        maxScroll: { y: maxScrollY, x: maxScrollX },
                        isAtTop: beforeTop === 0 && beforeLeft === 0,
                        canScrollFurther: {
                            y: afterTop < maxScrollY,
                            x: afterLeft < maxScrollX
                        }
                    };
                })();
            }""",
            {"x": center_x, "y": center_y, "dx": dx, "dy": dy},
        )

        # --- Validate JS result ---
        if not js_result or js_result.get("error"):
            logger.error(
                f"Scroll evaluation returned error: {js_result}", browser_context
            )
            return ToolResult(
                message="Could not evaluate or perform scroll on page", status="error"
            )

        axis = js_result.get("axis", "y")
        scrolled_pixels = js_result.get("scrolled", {}).get(axis, 0)
        max_scroll_axis = js_result.get("maxScroll", {}).get(axis, 0)
        after_pos = js_result.get("after", {}).get("top" if axis == "y" else "left", 0)
        before_pos = js_result.get("before", {}).get(
            "top" if axis == "y" else "left", 0
        )
        can_scroll_further = js_result.get("canScrollFurther", {}).get(axis, False)
        element_info = js_result.get("elementInfo")

        # --- Build human-friendly feedback ---
        # thresholds can be tuned
        NO_MOVE_THRESHOLD = 8  # pixels - consider this 'no meaningful movement'
        NEAR_LIMIT_THRESHOLD = 6  # pixels remaining to consider at limit

        if scrolled_pixels <= NO_MOVE_THRESHOLD:
            # If there was essentially no movement, check whether we're at the limit
            if (
                (
                    direction == "down"
                    and (max_scroll_axis - after_pos) <= NEAR_LIMIT_THRESHOLD
                )
                or (direction == "up" and after_pos <= NEAR_LIMIT_THRESHOLD)
                or (
                    direction == "right"
                    and (max_scroll_axis - after_pos) <= NEAR_LIMIT_THRESHOLD
                )
                or (direction == "left" and after_pos <= NEAR_LIMIT_THRESHOLD)
            ):
                msg = (
                    f"SCROLL LIMIT REACHED: Attempted to scroll {scroll_area_label} {direction}, "
                    f"but reached the {('bottom' if direction=='down' else 'top') if axis=='y' else ('right' if direction=='right' else 'left')} of the area. "
                    f"Element: {element_info}."
                )
                logger.debug(msg, browser_context)
                return ToolResult(message=msg)
            else:
                msg = (
                    f"LIMITED SCROLL: Attempted to scroll {scroll_area_label} {direction} by {int(abs(scroll_pixels))}px, "
                    f"but the content only moved {int(scrolled_pixels)}px. Element: {element_info}."
                )
                logger.debug(msg, browser_context)
                return ToolResult(message=msg)

        # Successful scroll
        remaining = 0
        if direction in ("down", "right"):
            remaining = max(0, int(max_scroll_axis - after_pos))
        else:
            remaining = max(0, int(after_pos))

        message = (
            f"SCROLLED: {scroll_area_label} scrolled {int(scrolled_pixels)} px {direction}. "
            f"Remaining on this axis ≈ {remaining} px. Element: {element_info}."
        )

        logger.debug(message, browser_context)
        return ToolResult(message=message)

    except Exception as e:
        logger.error(f"Error scrolling: {e}", browser_context)
        return ToolResult(message=f"Failed to scroll: {e}", status="error")


@tool_registry.register(
    is_active=lambda ctx: "select_dropdown_option" in ctx.reserved_tools
)
async def select_dropdown_option(
    element_index: int,
    option_index: int,  # TODO: handle multi-select with class Option:
    browser_context: Annotated[BrowserContext | None, InjectedToolArg] = None,
) -> ToolResult:
    """
    Selects an option from a dropdown by its index.
    """
    try:
        element_node = await browser_context.get_dom_element_by_index(element_index)

        if not element_node:
            logger.error(
                f"Element with index {element_index} not found.", browser_context
            )
            return ToolResult(
                message=f"Element {element_index} not found. Try Again", status="error"
            )

        asyncio.create_task(
            browser_context.animator.dropdown(
                element_node, text=f"Selecting option: {option_index}"
            )
        )

        # First check if it's a dropdown
        dropdown_info = await browser_context.is_element_dropdown(element_node)
        if not dropdown_info.get("is_dropdown", False):
            logger.error(
                f"Element {element_index} ({element_node.get_description()}) is not a dropdown.",
                browser_context,
            )
            return ToolResult(
                message=f"Element {element_index} ({element_node.get_description()}) is not a dropdown.",
                status="error",
            )

        # Get dropdown details to include in the response
        dropdown_details = await browser_context.get_dropdown_details(element_node)

        # Use the new method to select by index
        result = await browser_context.select_dropdown_option_by_index(
            element_node, option_index
        )

        if result.get("success"):
            selected_option = result.get("selected_option", {})
            option_text = selected_option.get("text", f"option at index {option_index}")

            logger.info(
                f"Selected option: {option_text} from dropdown element {element_index}({element_node.get_description()})",
                browser_context,
            )
            return ToolResult(
                message=f"Successfully selected '{option_text}' from dropdown element {element_index}.",
                data={
                    "selected_option": selected_option,
                    "all_options": dropdown_details.get("options", []),
                },
            )
        else:
            error_message = result.get("message", "Failed to select dropdown option")
            logger.error(
                f"Error selecting dropdown option: {error_message}", browser_context
            )
            return ToolResult(message=f"{error_message}", status="error")

    except Exception as e:
        logger.error(f"Error selecting dropdown option: {str(e)}", browser_context)
        return ToolResult(
            message=f"Error selecting dropdown option: {str(e)}", status="error"
        )


@tool_registry.register(is_active=lambda ctx: "find_by_selector" in ctx.reserved_tools)
async def find_by_selector(
    selector: str,
    browser_context: Annotated[BrowserContext | None, InjectedToolArg] = None,
) -> ToolResult:
    """Finds a single element using a unique CSS selector and scrolls it into view."""
    try:
        asyncio.create_task(
            browser_context.animator.processing(
                f"Finding element by selector: {selector}"
            )
        )
        page = await browser_context.get_agent_current_page()
        element = page.locator(selector).first
        count = await element.count()

        if count == 0:
            return ToolResult(
                message=f"No element found for selector: {selector}", status="error"
            )

        await element.evaluate("el => el.scrollIntoView({block: 'start'})")
        await page.wait_for_load_state("domcontentloaded", timeout=5000)

        text = await element.inner_text()

        return ToolResult(
            message=f"Successfully found and scrolled to element with text: '{text[:100]}'"
        )

    except Exception as e:
        logger.error(
            f"Failed to execute find_by_selector tool: {str(e)}", browser_context
        )
        return ToolResult(
            message=f"An unexpected error occurred while trying to find the element by selector: {str(e)}",
            status="error",
            reserve_tools=["find", "find_by_selector"],
        )


# @tool_registry.register()
async def commit(
    type: str,
    message: str,
    browser_context: Annotated[BrowserContext | None, InjectedToolArg] = None,
) -> ToolResult:
    """Saves the message to memory."""

    return Snippet(type=type, message=message)