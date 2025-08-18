import asyncio
from typing import Any, Annotated, Literal, TYPE_CHECKING
from pydantic import BaseModel, Field
from langchain_core.tools import InjectedToolArg
from logging_utils import get_toolkit_logger
from browser_use.context import BrowserContext
from .registry import tool_registry  # Import from the registry in the same directory
from .utils import get_extraction_plan
from readability import Document
from google import genai
from .types import ToolLogger as Log, ActionResult


@tool_registry.register()
async def type_text(
    element_index: int,
    text: str,
    press_enter: bool,
    browser_context: Annotated[BrowserContext | None, InjectedToolArg] = None,
) -> ActionResult:
    """Types text into a focused text field, identified by its numbered label."""

    element_node = await browser_context.get_dom_element_by_index(element_index)

    if not element_node:
        Log.debug(f"Element index {element_index} not found", browser_context)
        return ActionResult(error=f"Element index {element_index} not found")

    try:
        element_description = element_node.get_description()
        page = None

        if (
            element_node.tag_name == "button"
            or element_node.attributes.get("role") == "button"
        ):
            Log.warning(
                f"Element {element_index}({element_description}) is a button",
                browser_context,
            )
            return ActionResult(
                error=f"Element {element_index}({element_description}) is a button and cannot be typed into."
            )

        dropdown_info = await browser_context.is_element_dropdown(element_node)

        if dropdown_info.get("is_dropdown"):
            Log.info(
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
                    "If the selected option does not match your intent, use the select_dropdown_option tool with the correct option_index instead. "
                )
                return ActionResult(
                    message=message,
                    data={"selected_options": selected_options, "options": options},
                    reserve_tools=["select_dropdown_option"],
                )

            except Exception as e:
                Log.error(
                    f"Failed to interact with dropdown element {str(e)}",
                    browser_context,
                )
                return ActionResult(
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

        return ActionResult(message=message)

    except Exception as e:
        Log.error(
            f"Failed to type text into element {element_index}: {str(e)}",
            browser_context,
        )
        return ActionResult(
            error=f"Failed to type text into element {element_index}({element_node.get_description()})"
        )


@tool_registry.register(
    is_active=lambda ctx: False
    and (ctx.domain in ["about:blank", "www.google.com"] or ctx.step == 0)
)
async def google_search(
    query: str,
    browser_context: Annotated[BrowserContext | None, InjectedToolArg] = None,
) -> ActionResult:
    """Searches on google"""
    try:
        asyncio.create_task(browser_context.animator.processing(f"Searching '{query}'"))
        await browser_context.navigate_to(f"https://www.google.com/search?q={query}")
        return ActionResult(message=f"Searched the query: {query}")
    except Exception as e:
        Log.error(f"Google search failed: {str(e)}", browser_context)
        return ActionResult(message=f"Search failed: {str(e)}")


@tool_registry.register()
async def goto_url(
    url: str, browser_context: Annotated[BrowserContext | None, InjectedToolArg] = None
) -> ActionResult:
    """Navigates the browser to a specific URL endpoint as a direct web address e.g. www.linkedin.com/jobs"""
    try:
        if not url.startswith("http://") and not url.startswith("https://"):
            url = f"https://{url}"
        await browser_context.navigate_to(url)
        return ActionResult(message=f"Navigated to {url}")

    except Exception as e:
        Log.error(f"Failed to navigate to {url}: {str(e)}", browser_context)
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
            Log.debug(f"Element with index {element_index} not found.", browser_context)
            return ActionResult(error=f"Element index {element_index} not found.")

        dropdown_info = await browser_context.is_element_dropdown(element_node)
        if dropdown_info.get("is_dropdown", False):

            Log.info(
                f"Element {element_index}({element_node.get_description()}) is a dropdown.",
                browser_context,
            )
            asyncio.create_task(
                browser_context.animator.dropdown(
                    element_node, text="Getting dropdown options"
                )
            )

            dropdown_details = await browser_context.get_dropdown_details(element_node)
            message = (
                f"ACTION REQUIRED: Element {element_index}({element_node.get_description()}) is a dropdown menu "
                "that cannot be handled with a simple click. "
                "Please examine the available options below and use the select_dropdown_option tool "
                "with the appropriate option_index parameter to make your selection."
            )
            return ActionResult(
                message=message,
                data={
                    "selected_options": dropdown_details.get("selected_options", []),
                    "options": dropdown_details.get("options", []),
                },
                reserve_tools=["select_dropdown_option"],
            )

        session = await browser_context.get_session()
        initial_pages = len(session.context.pages)

        # if element has file uploader then dont click
        # if await browser_context.is_file_uploader(element_node):
        #     return ActionResult(message=f'Index {element_index} - has an element which opens file upload dialog. To upload files please use a specific function to upload files ')

        try:
            download_path = await browser_context._click_element_node(element_node)
            if download_path:
                message = f"Downloaded file to {download_path}"
            else:
                message = f"Clicked at element {element_index}({element_node.get_description()})"

        except Exception as click_error:
            Log.warning(
                f"Click encountered an error but may have succeeded: {str(click_error)}",
                browser_context,
            )
            message = f"Clicked at element {element_index}({element_node.get_description()}) - Note: Click succeeded but encountered post-click issues."

        session = await browser_context.get_session()
        if len(session.context.pages) > initial_pages:
            new_tab_msg = "New tab opened"
            message += f" - {new_tab_msg}"
            await browser_context.switch_to_tab(-1)

        return ActionResult(message=message)

    except Exception as e:
        Log.error(f"Click failed : {str(e)}", browser_context)
        return ActionResult(
            error=f"Failed to click element index {element_index}, most likely the state has changed."
        )


@tool_registry.register()
async def wait(
    seconds: int,
    browser_context: Annotated[BrowserContext | None, InjectedToolArg] = None,
) -> ActionResult:
    """Pauses execution. Use it to wait for content loading and user required actions or interactions."""
    Log.info(f"Waiting for {seconds} seconds...", browser_context)
    await asyncio.sleep(seconds)
    return ActionResult(message=f"Waited for {seconds} seconds")


@tool_registry.register(
    is_active=lambda ctx: ctx.last_action in ["scroll"] and ctx.step > 0
)
async def find(
    text: str,
    role: str,
    tag: str,
    browser_context: Annotated[BrowserContext | None, InjectedToolArg] = None,
) -> ActionResult:
    """Finds and scrolls to a specific element or text on the page. Provide semantic attributes like text(name), role, and tag for the most precise search."""

    try:
        page = await browser_context.get_agent_current_page()

        # --- Attempt #1: The "Perfect Match" (Highest Precision) ---
        locator = None
        count = 0

        Log.info(
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
            Log.info(f"Found and scrolled to element: '{text}'", browser_context)
            return ActionResult(
                message=f"Successfully found and scrolled to element: '{text}'"
            )

        # --- Attempt #2: The "Simple Text Fallback" ---
        Log.info(
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

            Log.info(f"Found and scrolled to element: '{text}'", browser_context)
            return ActionResult(message=f"Found and scrolled to element: '{text}'")

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

        Log.info(f"Found multiple elements matching '{text}'", browser_context)

        return ActionResult(
            message=f"Found multiple ({len(elements)}) elements matching '{text}'. Review the list and use the `find_by_selector` tool with the appropriate selector to proceed.",
            data=elements,
            reserve_tools=["find_by_selector"],
        )

    except Exception as e:
        Log.error(f"Failed to execute find tool: {str(e)}", browser_context)
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
            Log.info(
                f"Executing extract in 'element' mode for index {element_index}",
                browser_context,
            )
            element = await browser_context.get_dom_element_by_index(element_index)

            if not element:
                Log.error(
                    f"Element with index {element_index} not found for extraction",
                    browser_context,
                )
                return ActionResult(
                    error=f"Element with index {element_index} not found."
                )

            contextual_snippet = element.get_contextual_dom_text()
            Log.debug(
                f"Contextual DOM Snippet: size: {len(contextual_snippet)}",
                browser_context,
            )

            plan = await get_extraction_plan(
                query=query,
                dom=contextual_snippet,
                element_index=element_index,
                element_description=element.get_description(),
            )
            Log.debug(f"Generated extraction plan: {plan}", browser_context)

            goal = plan.goal
            selector = plan.selector

        else:
            Log.info(
                f"Executing extract in 'discovery' mode for query: '{query}'",
                browser_context,
            )

            simplified_dom = (
                browser_context.current_state.element_tree.get_simplified_dom_text()
            )
            Log.debug(
                f"Simplified DOM with len: {len(simplified_dom)}", browser_context
            )

            # FIXME: use the user provided goal also to generate more accurate extraction plans.
            plan = await get_extraction_plan(query=query, dom=simplified_dom)
            Log.debug(f"Generated extraction plan: {plan}", browser_context)

            goal = plan.goal
            selector = plan.selector

        try:
            if goal == "MAIN_CONTENT":
                Log.info(
                    "Extracting main content using readability...", browser_context
                )
                html_content = await page.content()
                doc = Document(html_content)
                main_content_html = doc.summary(html_partial=True)
                Log.debug(
                    f"Extracted main content for article, length: {len(main_content_html)}",
                    browser_context,
                )
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
                Log.warning(
                    f"No elements found for selector: {selector}", browser_context
                )
                return ActionResult(
                    message=f"The generated selector '{selector}' did not find any elements."
                )

            if goal == "SINGLE_ITEM":
                Log.info(
                    f"Extracting single item for query: '{query}'", browser_context
                )
                data = await elements.first.inner_text()
                Log.debug(
                    f"Extracted text for query: '{query[:50]}...'", browser_context
                )
                return ActionResult(
                    message=f"Extracted text for query: '{query}'", data=data
                )

            elif goal == "LIST_OF_ITEMS":
                Log.info(
                    f"Extracting list of items for query: '{query}'", browser_context
                )
                data = await elements.all_inner_texts()
                Log.debug(
                    f"Extracted {len(data)} items for query: '{query}', Data: \n{data[:10]}...",
                    browser_context,
                )  # Log first 10 items for debugging
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
            Log.error(f"Failed to execute extract tool: {str(e)}", browser_context)
            return ActionResult(
                error=f"An unexpected error occurred during extraction: {str(e)}"
            )

    except Exception as e:
        Log.error(f"Failed to execute extract tool: {str(e)}", browser_context)
        return ActionResult(
            error=f"An unexpected error occurred during extraction: {str(e)}"
        )


@tool_registry.register()
async def finish_task(
    is_task_completed: bool,
    reason: str = Field(
        description="The detailed reason why the task is considered finished."
    ),
    browser_context: Annotated[BrowserContext | None, InjectedToolArg] = None,
) -> ActionResult:
    """Finishes the running task."""
    Log.info(
        f"Task {'Completed' if is_task_completed else 'Failed'}, reason: {reason}",
        browser_context,
    )
    return ActionResult(
        message=f"Task {'Completed' if is_task_completed else 'Failed'} because {reason}"
    )


@tool_registry.register(is_active=lambda ctx: ctx.text_field_focused)
async def press_keys(
    keys: str, browser_context: Annotated[BrowserContext | None, InjectedToolArg] = None
) -> ActionResult:
    """Simulates key press or keyboard shortcuts. e.g. 'Enter', 'Control+A' etc."""
    try:
        asyncio.create_task(browser_context.animator.key(keys))
        page = await browser_context.get_agent_current_page()
        await page.keyboard.press(keys)
        return ActionResult(message=f"Pressed keys: {keys}")
    except Exception as e:
        Log.error(f"Failed to press keys '{keys}': {str(e)}", browser_context)
        return ActionResult(error=f"Failed to press keys '{keys}': {str(e)}")


@tool_registry.register()
async def scroll(
    bounding_box: list[int],
    direction: str,
    scroll_area: str,
    browser_context: Annotated[BrowserContext | None, InjectedToolArg] = None,
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
            Log.error("Could not determine viewport size", browser_context)
            return ActionResult(error="Could not determine viewport size")

        height, width = viewport.get("height"), viewport.get("width")

        ymin, xmin, ymax, xmax = bounding_box

        # Calculate target coordinates
        y = ((ymin + ymax) / 2) / 1000 * height
        x = ((xmin + xmax) / 2) / 1000 * width

        # Check if the area is scrollable
        is_area_scrollable = await page.evaluate(
            """
            (x, y) => {
                // Get the element at the specified coordinates
                let element = document.elementFromPoint(x, y);
                if (!element) return { scrollable: false };
                
                // Find scrollable parent if current element isn't scrollable
                let current = element;
                while (current && current !== document.body && current !== document.documentElement) {
                    const style = window.getComputedStyle(current);
                    const overflowY = style.overflowY || style.overflow;
                    
                    if (['scroll', 'auto', 'overlay'].includes(overflowY) && 
                        current.scrollHeight > current.clientHeight) {
                        return {
                            scrollable: true,
                            element: current,
                            scrollHeight: current.scrollHeight,
                            clientHeight: current.clientHeight,
                            scrollTop: current.scrollTop,
                            maxScroll: current.scrollHeight - current.clientHeight
                        };
                    }
                    current = current.parentElement;
                }
                
                // Check if page itself is scrollable
                const docScrollHeight = document.documentElement.scrollHeight || document.body.scrollHeight;
                const docClientHeight = document.documentElement.clientHeight || window.innerHeight;
                if (docScrollHeight > docClientHeight) {
                    return {
                        scrollable: true,
                        element: null,  // null means document/page scroll
                        scrollHeight: docScrollHeight,
                        clientHeight: docClientHeight,
                        scrollTop: document.documentElement.scrollTop || document.body.scrollTop,
                        maxScroll: docScrollHeight - docClientHeight
                    };
                }
                
                return { scrollable: false };
            }
        """,
            x,
            y,
        )

        if not is_area_scrollable["scrollable"]:
            return ActionResult(
                error=f"The {scroll_area} area is not scrollable. Try a different area or approach."
            )

        # Move mouse to target area
        asyncio.create_task(
            browser_context.animator.scroll(
                direction,
                coords={"x": x, "y": y},
                text="Scrolling using spatial understanding",
            )
        )

        # Get scroll position before scrolling
        scroll_before = await page.evaluate(
            """
            (x, y, isDocScroll) => {
                if (isDocScroll) {
                    return window.pageYOffset || document.documentElement.scrollTop;
                } else {
                    const el = document.elementFromPoint(x, y);
                    return el ? el.scrollTop : 0;
                }
            }
        """,
            x,
            y,
            is_area_scrollable["element"] is None,
        )

        # Perform the scroll
        amount = 700
        scroll_delta_y = amount if direction == "down" else -amount
        # FIXME: Use the locator to run scrollBy or scrollTop += delta on the exact element rather than rely on mouse.wheel
        await page.mouse.move(x, y)
        await page.mouse.wheel(0, scroll_delta_y)
        await page.wait_for_timeout(500)

        # Get scroll position after scrolling
        scroll_after = await page.evaluate(
            """
            (x, y, isDocScroll) => {
                if (isDocScroll) {
                    return window.pageYOffset || document.documentElement.scrollTop;
                } else {
                    const el = document.elementFromPoint(x, y);
                    return el ? el.scrollTop : 0;
                }
            }
        """,
            x,
            y,
            is_area_scrollable["element"] is None,
        )

        actual_scroll = abs(scroll_after - scroll_before)

        # Determine remaining scroll
        max_remaining = 0
        if direction == "down":
            max_remaining = is_area_scrollable["maxScroll"] - scroll_after
        else:  # Scrolling up
            max_remaining = scroll_after

        # Build informative message
        if actual_scroll < 50:  # Very little or no scroll happened
            if max_remaining < 10:  # Essentially at the limit
                Log.debug(f"Scroll Limit Reached", browser_context)
                return ActionResult(
                    message=(
                        f"SCROLL LIMIT REACHED: You've reached the {direction == 'down' and 'bottom' or 'top'} of {scroll_area}. "
                        f"No further scrolling possible {direction}wards. "
                        "Figure out the next appropriate action to take to continue the task."
                    )
                )
            else:
                Log.debug(
                    f"Attempted to scroll: {actual_scroll} but only moved: {actual_scroll} pixels",
                    browser_context,
                )
                return ActionResult(
                    message=(
                        f"LIMITED SCROLL: {scroll_area} has restricted scrollability. "
                        f"Attempted to scroll but only moved {actual_scroll} pixels. "
                    )
                )

        message = f"Scrolled {scroll_area} by {actual_scroll} pixels {direction}wards."

        if max_remaining > 100:
            message += f" Approximately {max_remaining} pixels remaining to scroll {direction}."

        Log.debug(f"{message}", browser_context)
        return ActionResult(message=message)

    except Exception as e:
        Log.error(f"Error scrolling: {e}", browser_context)
        return ActionResult(error=f"Failed to scroll")


@tool_registry.register(
    is_active=lambda ctx: "select_dropdown_option" in ctx.reserved_tools
)
async def select_dropdown_option(
    element_index: int,
    option_index: int,  # TODO: handle multi-select
    browser_context: Annotated[BrowserContext | None, InjectedToolArg] = None,
) -> ActionResult:
    """
    Selects an option from a dropdown by its index.
    """
    try:
        element_node = await browser_context.get_dom_element_by_index(element_index)

        if not element_node:
            Log.error(f"Element with index {element_index} not found.", browser_context)
            return ActionResult(error=f"Element {element_index} not found. Try Again")

        asyncio.create_task(
            browser_context.animator.dropdown(
                element_node, text=f"Selecting option: {option_index}"
            )
        )

        # First check if it's a dropdown
        dropdown_info = await browser_context.is_element_dropdown(element_node)
        if not dropdown_info.get("is_dropdown", False):
            Log.error(
                f"Element {element_index} ({element_node.get_description()}) is not a dropdown.",
                browser_context,
            )
            return ActionResult(
                error=f"Element {element_index} ({element_node.get_description()}) is not a dropdown."
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

            Log.info(
                f"Selected option: {option_text} from dropdown element {element_index}({element_node.get_description()})",
                browser_context,
            )
            return ActionResult(
                message=f"Successfully selected '{option_text}' from dropdown element {element_index}.",
                data={
                    "selected_option": selected_option,
                    "all_options": dropdown_details.get("options", []),
                },
            )
        else:
            error_message = result.get("message", "Failed to select dropdown option")
            Log.error(
                f"Error selecting dropdown option: {error_message}", browser_context
            )
            return ActionResult(error=f"{error_message}")

    except Exception as e:
        Log.error(f"Error selecting dropdown option: {str(e)}", browser_context)
        return ActionResult(error=f"Error selecting dropdown option: {str(e)}")


@tool_registry.register(is_active=lambda ctx: "find_by_selector" in ctx.reserved_tools)
async def find_by_selector(
    selector: str,
    browser_context: Annotated[BrowserContext | None, InjectedToolArg] = None,
) -> ActionResult:
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
            return ActionResult(error=f"No element found for selector: {selector}")

        await element.evaluate("el => el.scrollIntoView({block: 'start'})")
        await page.wait_for_load_state("domcontentloaded", timeout=5000)

        text = await element.inner_text()

        return ActionResult(
            message=f"Successfully found and scrolled to element with text: '{text[:100]}'"
        )

    except Exception as e:
        Log.error(f"Failed to execute find_by_selector tool: {str(e)}", browser_context)
        return ActionResult(
            error=f"An unexpected error occurred while trying to find the element by selector: {str(e)}",
            reserve_tools=["find", "find_by_selector"],
        )
