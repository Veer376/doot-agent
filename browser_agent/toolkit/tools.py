import asyncio
from typing import Any, Annotated
from pydantic import BaseModel, Field
from typing import Literal
from langchain_core.tools import InjectedToolArg
import logging
from browser_use.context import BrowserContext
from typing import TYPE_CHECKING
from .registry import tool_registry, MetaData  # Import from the registry in the same directory
from .utils.llm_helper import get_extraction_plan
from readability import Document

logger = logging.getLogger(__name__)

# FIXME: add label: str and expected_output: str to force the LLM for browser reasoning, may lead to better accuracy.

class ActionResult(BaseModel):
    message: str | None = None
    error: str | None = None
    data: Any = None

    def __str__(self):
        return str(self.model_dump(exclude_none=True))


@tool_registry.register(metadata=MetaData(
    allowed_domains=["about:blank", "www.google.com"],
))
async def google_search(
    query: str, 
    browser_context: Annotated[BrowserContext|None, InjectedToolArg] = None
) -> ActionResult:
    # TODO: add the description to use it this as the grounding technique.
    """Searches on google"""
    try:
        await browser_context.navigate_to(f"https://www.google.com/search?q={query}")
        return ActionResult(message=f"Searched the query: {query}")
    except Exception as e:
        return ActionResult(message=f"Search failed: {str(e)}")
  

# TODO: we can always navigate the url in the new tab, eliminating the need of create_tab tool.
@tool_registry.register()
async def goto_to_url(
    url: str, 
    browser_context: Annotated[BrowserContext|None, InjectedToolArg] = None
) -> ActionResult:
    """Navigates the browser to a specific URL endpoint as a direct web address e.g. linkedin.com/jobs"""
    try:
        await browser_context.navigate_to(url)
        return ActionResult(message=f"Navigated to {url}")

    except Exception as e:
        return ActionResult(error=f"Failed to navigate to {url}. {str(e)}")


@tool_registry.register()
async def click_element(
    element_index: int, browser_context: Annotated[BrowserContext|None, InjectedToolArg] = None
) -> ActionResult:
    """Clicks an interactive element, such as a button or link, identified by its numbered label."""

    element_node = await browser_context.get_dom_element_by_index(element_index)
    if not element_node:
        return ActionResult(error=f"Element index {element_index} not found")

    try:
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
            message = f"Clicked at '{element_node.get_description()}'."

        session = await browser_context.get_session()
        if len(session.context.pages) > initial_pages:
            new_tab_msg = "New tab opened"
            message += f" - {new_tab_msg}"
            await browser_context.switch_to_tab(-1)

        return ActionResult(message=message)

    except Exception as e:
        logger.error(f"Click failed : {str(e)}")
        return ActionResult(
            error=f"Click failed, most likely the state has changed. {str(e)}"
        )


@tool_registry.register()
async def type_text(
    element_index: int,
    text: str,
    press_enter: bool = False, # saving one LLM call.
    browser_context: Annotated[BrowserContext|None, InjectedToolArg] = None,
) -> ActionResult:
    """Types text directly into a textfield, identified by its numbered label. Use press_enter to send, search, or submit."""

    try:
        element_node = await browser_context.get_dom_element_by_index(element_index)
        if not element_node:
            return ActionResult(error=f"Element index {element_index} not found")

        element_description = element_node.get_description()

        # TODO: add more checks.
        if (
            element_node.tag_name == "button"
            or element_node.attributes.get("role") == "button"
        ):
            return ActionResult(
                error=f"Element '{element_description}' with label {element_index} is a button"
            )

        await browser_context._input_text_element_node(element_node, text)
        message = f"Typed text: '{text}' in '{element_description}'"
        # FIXME: implement press_keys in browser_context and handle the stale state if type text fails.
        if press_enter:
            page = await browser_context.get_agent_current_page()
            await page.keyboard.press("Enter")
            message += " and sent it by pressing Enter key"

        return ActionResult(message=message)

    except Exception as e:
        logger.error(
            f"Failed to type text into element index {element_index}: {str(e)}"
        )
        return ActionResult(
            error=f"Failed to type text into '{element_node.get_description()}' with index {element_index}"
        )


# FIXME: we can reduce the wait tool request in case of content loading, based on the no. interative element present - in context.py
@tool_registry.register()
async def wait(
    seconds: int, browser_context: Annotated[BrowserContext|None, InjectedToolArg] = None
) -> ActionResult:
    """Pauses execution during loading or login processes etc."""
    await asyncio.sleep(max(10, seconds))
    return ActionResult(message=f"Waited for {seconds} seconds")


@tool_registry.register()
async def scroll(
    amount: int = 600,
    element_index: int|None = None,
    browser_context: Annotated[BrowserContext|None, InjectedToolArg] = None
) -> ActionResult:
    """
    Scrolls the page or a specific element using the mouse wheel for robustness.
    """
    page = await browser_context.get_current_page()

    if element_index is not None:
        # --- Scroll a specific element ---
        element = await browser_context.get_dom_element_by_index(element_index)
        if not element:
            return ActionResult(error=f"Element with index {element_index} not found.")

        bbox = element.bounding_box
        if not bbox:
             return ActionResult(error=f"Could not get the bounding box for element {element_index}.")

        # Position the mouse over the center of the element
        mouse_x = bbox['x'] + bbox['width'] / 2
        mouse_y = bbox['y'] + bbox['height'] / 2
        await page.mouse.move(mouse_x, mouse_y)
        
        await page.mouse.wheel(0, amount)
        
        target_info = f"element at index {element_index}"

    else:
        await page.mouse.wheel(0, amount)
        target_info = "the main page"

    scroll_direction = "down" if amount > 0 else "up"
    message = f"Successfully scrolled {target_info} {scroll_direction} by {abs(amount)} pixels."
    print(message)
    return ActionResult(message=message)

# FIXME: we can remove this at all, if the plan is provided to the LLM.
@tool_registry.register()
async def find(
    name: str,
    role: str,
    tag: str,
    browser_context: Annotated[BrowserContext|None, InjectedToolArg] = None,
) -> ActionResult:
    """Finds and scrolls to a specific element or text on the page. Provide semantic attributes like name, role, and tag for the most precise search."""

    page = await browser_context.get_agent_current_page()
    
    try:
        # --- Attempt #1: The "Perfect Match" (Highest Precision) ---
        locator = None
        count = 0
        
        if name and role and tag:
            locator = page.locator(f"{tag}").filter(has=page.get_by_role(role, name=name, exact=False))
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
            await page.wait_for_load_state('domcontentloaded', timeout=5000)
            return ActionResult(message=f"Successfully found and scrolled to element: '{name}'")

        # --- Attempt #2: The "Simple Text Fallback" ---
        print("Precise match failed or was not possible. Falling back to simple text search.")
        locator = page.get_by_text(name, exact=False)
        
        count = await locator.count()
        if count == 1:
            element = locator.first
            # Scrolling the element at the very start.
            await element.evaluate("el => el.scrollIntoView({block: 'start'})")
            await page.wait_for_load_state('domcontentloaded', timeout=5000)
            return ActionResult(message=f"Successfully found and scrolled to element: '{name}'")
        
        elements = []
        for i in range(count):
            element = locator.nth(i)
            element_info = {
                "index": i,
                "text": await element.inner_text(),
                "tag": await element.evaluate('(element) => element.tagName.toLowerCase()'),
                "role": await element.evaluate('(element) => element.getAttribute("role")') or "none",
            }
            elements.append(element_info)
            
    
        # FIXME: --- Step 3: Handle Ambiguity Using LLM. ---
        return ActionResult(
            message=f"Found multiple ({len(elements)}) elements matching '{name}'. Disambiguation is required.",
            data=elements
        )

    except Exception as e:
        logger.error(f"Failed to execute find tool: {str(e)}")
        return ActionResult(error=f"An unexpected error occurred while trying to find the element: {str(e)}")
   
  
@tool_registry.register()
async def extract(
    query: str,
    element_index: int|None,
    browser_context: Annotated[BrowserContext|None, InjectedToolArg] = None,
) -> ActionResult:
    """Extracts content of the viewport or complete page when a manual reading is complex. Use it to get the full text of an article, extract structured data like tables, lists, images etc.
query: A clear, natural language description of the information you need. e.g. 'the main content of the article', 'a list of all user comments', 'the financial data table'
element_index: Use to extract a single item directly, or provide as an example to extract a list of similar items (if available in browser state)
"""
    
    page = await browser_context.get_agent_current_page()

    try:
        
        goal = None
        selector = None
        
        import re
        main_content_pattern = re.compile(r'\b(main|article|body|content|post|text)\b', re.IGNORECASE)

        if main_content_pattern.search(query) and element_index is None:
            goal = "MAIN_CONTENT"
            
        elif element_index is not None:
            logger.info(f"Executing extract in 'element' mode for index {element_index}")
            element = await browser_context.get_dom_element_by_index(element_index)
            
            if not element:
                return ActionResult(error=f"Element with index {element_index} not found.")
            
            contextual_snippet = element.get_contextual_dom_text(ancestor_levels=2)
            print(f"Contextual DOM Snippet: size: {len(contextual_snippet)} \n {contextual_snippet}")
            
            plan = await get_extraction_plan(query=query, dom=contextual_snippet, element_index=element_index, element_description=element.get_description())
            print(f"Generated extraction plan: {plan}")
            
            goal = plan.goal
            selector = plan.selector
            
            if not selector:
                raise ValueError(f"The extraction strategist failed to provide a selector for the goal '{goal}'.")
            
        else:
            logger.info(f"Executing extract in 'discovery' mode for query: '{query}'")
        
            simplified_dom = browser_context.current_state.element_tree.get_simplified_dom_text()
            print(f"Simplified DOM with len: {len(simplified_dom)}")
        
            # FIXME: use the user provided goal also to generate more accurate extraction plans.
            plan = await get_extraction_plan(query=query, dom=simplified_dom)
            print(f"Generated extraction plan: {plan}")
            
            goal = plan.goal
            selector = plan.selector
            
            if not selector:
                raise ValueError(f"The extraction strategist failed to provide a selector for the goal '{goal}'.")
            
            
        try:    
            if goal == "MAIN_CONTENT":
                print("Extracting main content using readability...")
                html_content = await page.content()
                doc = Document(html_content)
                main_content_html = doc.summary(html_partial=True)
                print(f"Extracted main content for article: '{len(main_content_html)}'")
                return ActionResult(message=f"Extracted main content for article: '{doc.title()}'", data=main_content_html)

            if not selector:
                return ActionResult(error=f"The extraction strategist failed to provide a selector for the goal '{goal}'.")

            elements = page.locator(selector)
            count = await elements.count()
            if count == 0:
                print(f"No elements found for selector: {selector}")
                return ActionResult(message=f"The generated selector '{selector}' did not find any elements.")

            if goal == "SINGLE_ITEM":
                print(f"Extracting single item for query: '{query}'")
                data = await elements.first.inner_text()
                print(f"Extracted text for query: '{data}'")
                return ActionResult(message=f"Extracted text for query: '{query}'", data=data)

            elif goal == "LIST_OF_ITEMS":
                print(f"Extracting list of items for query: '{query}'")
                data = await elements.all_inner_texts()
                print(f"Extracted {len(data)} items for query: '{query}', Data: \n{data}...")  # Print first 10 items for debugging
                return ActionResult(message=f"Extracted {len(data)} items for query: '{query}'", data=data)

            # elif goal == "TABLE":
            #     table_data = await _extract_table_data(elements.first)
            #     return ActionResult(message=f"Extracted table with {len(table_data)} rows.", data=table_data)
            
            else:
                return ActionResult(error=f"Unknown goal '{goal}' returned by strategist.")
        except Exception as e:
            logger.error(f"Failed to execute extract tool: {str(e)}")
            return ActionResult(error=f"An unexpected error occurred during extraction: {str(e)}")
        
    except Exception as e:
        logger.error(f"Failed to execute extract tool: {str(e)}")
        return ActionResult(error=f"An unexpected error occurred during extraction: {str(e)}")


# TODO: implement this tool to exit with a evaluation and report.
@tool_registry.register()
async def exit_session(
    reason: Literal["goal_achieved", "error", "need more tools"],
    description: str,
    browser_context: Annotated[BrowserContext|None, InjectedToolArg] = None,
) -> ActionResult:
    pass


# FIXME: add the tool only when a text field is in focus.
# @tool_registry.register()
async def press_keys(
    keys: str, browser: Annotated[BrowserContext|None, InjectedToolArg] = None
) -> ActionResult:
    """Simulates key press or keyboard shortcuts. e.g. 'Enter', 'Control+A' etc."""
    page = await browser.get_agent_current_page()
    try:
        # TODO: We might we using the delay after 'enter'
        await page.keyboard.press(keys)
        return ActionResult(message=f"Pressed keys: {keys}")
    except Exception as e:
        return ActionResult(error=f"Failed to press keys '{keys}': {str(e)}")
