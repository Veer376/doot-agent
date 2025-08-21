import asyncio
import base64
import gc
import json
import logging
import os
import re
import time
import uuid
from dataclasses import dataclass
from typing import TYPE_CHECKING
import anyio
from playwright._impl._errors import TimeoutError
from playwright.async_api import Browser as PlaywrightBrowser
from playwright.async_api import (
    BrowserContext as PlaywrightBrowserContext,
)
from playwright.async_api import (
    ElementHandle,
    FrameLocator,
    Page,
)
from pydantic import BaseModel, ConfigDict, Field
from .types import (
    BrowserError,
    BrowserState,
    TabInfo,
    URLNotAllowedError,
)
from .dom.clickable_element_processor.service import ClickableElementProcessor
from .dom.service import DomService
from .dom.types import DOMElementNode, SelectorMap
from .utils import time_execution_async, time_execution_sync
from .animator import Animator

if TYPE_CHECKING:
    from .browser import Browser

logger = logging.getLogger(__name__)

import platform

BROWSER_NAVBAR_HEIGHT = {
    "windows": 85,
    "darwin": 80,
    "linux": 90,
}.get(platform.system().lower(), 85)

_GLOB_WARNING_SHOWN = False


class BrowserContextConfig(BaseModel):
    """
    Configuration for the BrowserContext.

    Default values:
            cookies_file: None
                    Path to cookies file for persistence

            disable_security: False
                    Disable browser security features (dangerous, but cross-origin iframe support requires it)

            minimum_wait_page_load_time: 0.5
                    Minimum time to wait before getting page state for LLM input

            wait_for_network_idle_page_load_time: 1.0
                    Time to wait for network requests to finish before getting page state.
                    Lower values may result in incomplete page loads.

            maximum_wait_page_load_time: 5.0
                    Maximum time to wait for page load before proceeding anyway

            wait_between_actions: 1.0
                    Time to wait between multiple per step actions

            window_width: 1280
            window_height: 1100
                    Default browser window dimensions

            no_viewport: True
                    When True (default), the browser window size determines the viewport.
                    When False, forces a fixed viewport size using window_width and window_height. (constraint of the rendered content to a smaller area than the default of the entire window size)

            save_recording_path: None
                    Path to save video recordings

            save_downloads_path: None
                    Path to save downloads to

            trace_path: None
                    Path to save trace files. It will auto name the file with the TRACE_PATH/{context_id}.zip

            locale: None
                    Specify user locale, for example en-GB, de-DE, etc. Locale will affect navigator.language value, Accept-Language request header value as well as number and date formatting rules. If not provided, defaults to the system default locale.

            user_agent: 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/85.0.4183.102 Safari/537.36'
                    custom user agent to use.

            highlight_elements: True
                    Highlight elements in the DOM on the screen

            viewport_expansion: 0
                    Viewport expansion in pixels. This amount will increase the number of elements which are included in the state what the LLM will see. If set to -1, all elements will be included (this leads to high token usage). If set to 0, only the elements which are visible in the viewport will be included.

            allowed_domains: None
                    List of allowed domains that can be accessed. If None, all domains are allowed.
                    Example: ['example.com', 'api.example.com']

            include_dynamic_attributes: bool = True
                    Include dynamic attributes in the CSS selector. If you want to reuse the css_selectors, it might be better to set this to False.

              http_credentials: None
      Dictionary with HTTP basic authentication credentials for corporate intranets (only supports one set of credentials for all URLs at the moment), e.g.
      {"username": "bill", "password": "pa55w0rd"}

            is_mobile: None
                    Whether the meta viewport tag is taken into account and touch events are enabled.

            has_touch: None
                    Whether to enable touch events in the browser.

            geolocation: None
                    Geolocation to be used in the browser context. Example: {'latitude': 59.95, 'longitude': 30.31667}

            permissions: ['clipboard-read', 'clipboard-write']
                    Browser permissions to grant. See full list here: https://playwright.dev/python/docs/api/class-browsercontext#browser-context-grant-permissions

            timezone_id: None
                    Changes the timezone of the browser. Example: 'Europe/Berlin'

            force_new_context: False
                    Forces a new browser context to be created. Useful when running locally with branded browser (e.g Chrome, Edge) and setting a custom config.
    """

    model_config = ConfigDict(
        arbitrary_types_allowed=True,
        extra="ignore",
        populate_by_name=True,
        from_attributes=True,
        validate_assignment=True,
        revalidate_instances="subclass-instances",
    )

    cookies_file: str | None = None
    minimum_wait_page_load_time: float = 0.25
    wait_for_network_idle_page_load_time: float = 0.5
    maximum_wait_page_load_time: float = 5
    wait_between_actions: float = 0.5

    disable_security: bool = (
        False  # disable_security=True is dangerous as any malicious URL visited could embed an iframe for the user's bank, and use their cookies to steal money
    )

    window_width: int = 1280
    window_height: int = 1100
    no_viewport: bool = (
        True  # True is the default for headful mode - browser window size determines viewport
    )

    save_recording_path: str | None = None
    save_downloads_path: str | None = None
    save_har_path: str | None = None
    trace_path: str | None = None
    locale: str | None = None
    user_agent: str | None = None

    highlight_elements: bool = True
    viewport_expansion: int = 0
    allowed_domains: list[str] | None = None
    include_dynamic_attributes: bool = True
    http_credentials: dict[str, str] | None = None

    keep_alive: bool = Field(
        default=False, alias="_force_keep_context_alive"
    )  # used to be called _force_keep_context_alive
    is_mobile: bool | None = None
    has_touch: bool | None = None
    geolocation: dict | None = None
    permissions: list[str] = Field(
        default_factory=lambda: [
            "clipboard-read",
            "clipboard-write",
        ]
    )
    timezone_id: str | None = None

    force_new_context: bool = False

    # TODO: implement trigger.
    animate_actions: bool = True


@dataclass
class CachedStateClickableElementsHashes:
    """
    Clickable elements hashes for the last state
    """

    url: str
    hashes: set[str]


class BrowserSession:
    def __init__(
        self,
        context: PlaywrightBrowserContext,
        cached_state: BrowserState | None = None,
    ):
        self.context = context
        self.cached_state = cached_state

        self.cached_state_clickable_elements_hashes: (
            CachedStateClickableElementsHashes | None
        ) = None


@dataclass
class BrowserContextState:
    """
    State of the browser context
    """

    target_id: str | None = (
        None  # CDP target ID #TODO: Make sure that it gets saved in the state.
    )


class BrowserContext:
    def __init__(
        self,
        browser: "Browser",
        config: BrowserContextConfig | None = None,
        state: BrowserContextState | None = None,
    ):
        self.context_id = str(uuid.uuid4())

        self.config = config or BrowserContextConfig(
            **(browser.config.model_dump() if browser.config else {})
        )
        self.browser = browser

        self.state = state or BrowserContextState()

        # Initialize these as None - they'll be set up when needed
        self.session: BrowserSession | None = None
        self.animator = Animator(None)

        # Tab references - separate concepts for agent intent and browser state
        self.agent_current_page: Page | None = (
            None  # The tab the agent intends to interact with
        )
        self.human_current_page: Page | None = (
            None  # The tab currently shown in the browser UI
        )

    async def __aenter__(self):
        """Async context manager entry"""
        await self._initialize_session()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit"""
        await self.close()

    @time_execution_async("--close")
    async def close(self):
        """Close the browser instance"""

        try:
            if self.session is None:
                return

            # Then remove CDP protocol listeners
            if self._page_event_handler and self.session.context:
                try:
                    # This actually sends a CDP command to unsubscribe
                    self.session.context.remove_listener(
                        "page", self._page_event_handler
                    )
                except Exception as e:
                    logger.debug(f"Failed to remove CDP listener: {e}")
                self._page_event_handler = None

            await self.save_cookies()

            if self.config.trace_path:
                try:
                    await self.session.context.tracing.stop(
                        path=os.path.join(
                            self.config.trace_path, f"{self.context_id}.zip"
                        )
                    )
                except Exception as e:
                    logger.debug(f"Failed to stop tracing: {e}")

            # This is crucial - it closes the CDP connection
            if not self.config.keep_alive:
                logger.debug("Closing browser context")
                try:
                    await self.session.context.close()
                except Exception as e:
                    logger.debug(f"Failed to close context: {e}")
        finally:
            # Dereference everything
            self.agent_current_page = None
            self.human_current_page = None
            self.session = None
            self._page_event_handler = None

    def __del__(self):
        """Cleanup when object is destroyed"""
        if not self.config.keep_alive and self.session is not None:
            logger.debug("BrowserContext was not properly closed before destruction")
            try:
                if hasattr(self, "close") and asyncio is not None:
                    try:
                        asyncio.run(self.close())
                    except RuntimeError as e:
                        if "Event loop is closed" in str(e):
                            # This happens during interpreter shutdown.
                            # We can create a new loop to run the cleanup.
                            loop = asyncio.new_event_loop()
                            asyncio.set_event_loop(loop)
                            try:
                                loop.run_until_complete(self.close())
                            finally:
                                loop.close()
                                asyncio.set_event_loop(None)
                        else:
                            # Other runtime errors should be reported.
                            logger.warning(f"RuntimeError during BrowserContext cleanup: {e}")

            except Exception as e:
                logger.warning(f"Failed to force close browser context: {e}")
            finally:
                self.session = None
                self.agent_current_page = None
                self.human_current_page = None
                if gc is not None:
                    gc.collect()

    @time_execution_async("--initialize_session")
    async def _initialize_session(self):
        """Initialize the browser session"""
        logger.debug(f"🌎  Initializing new browser context with id: {self.context_id}")

        playwright_browser = await self.browser.get_playwright_browser()
        context = await self._create_context(playwright_browser)
        self._page_event_handler = None

        # auto-attach the foregrounding-detection listener to all new pages opened

        context.on("page", self._add_tab_foregrounding_listener)

        # TODO: what if we make it asyncio.
        # await context.add_init_script(self.animator.animator_script)

        # Get or create a page to use
        pages = context.pages

        self.session = BrowserSession(
            context=context,
            cached_state=None,
        )

        current_page = None
        if self.browser.config.cdp_url:
            # If we have a saved target ID, try to find and activate it
            if self.state.target_id:
                targets = await self._get_cdp_targets()
                for target in targets:
                    if target["targetId"] == self.state.target_id:
                        # Find matching page by URL
                        for page in pages:
                            if page.url == target["url"]:
                                current_page = page
                                break
                        break

        # If no target ID or couldn't find it, use existing page or create new
        if not current_page:
            if (
                pages
                and pages[0].url
                and not pages[0].url.startswith(
                    "chrome://"
                )  # skip chrome internal pages e.g. settings, history, etc
                and not pages[0].url.startswith(
                    "chrome-extension://"
                )  # skip hidden extension background pages
            ):
                current_page = pages[0]
                logger.debug("🔍  Using existing page: %s", current_page.url)
            else:
                current_page = await context.new_page()
                await current_page.goto("about:blank")
                logger.debug("🆕  Created new page: %s", current_page.url)

            # Get target ID for the active page
            if self.browser.config.cdp_url:
                targets = await self._get_cdp_targets()
                for target in targets:
                    if target["url"] == current_page.url:
                        self.state.target_id = target["targetId"]
                        break
        # Bring page to front
        logger.debug("🫨  Bringing tab to front: %s", current_page)
        await current_page.bring_to_front()
        await current_page.wait_for_load_state("load")

        # Set the viewport size for the active page
        await self.set_viewport_size(current_page)

        # Initialize both tab references to the same page initially
        self.agent_current_page = current_page
        self.human_current_page = current_page
        self.animator.page = current_page

        # Set up visibility listeners for all existing tabs
        for page in pages:
            if (
                not page.url.startswith("chrome-extension://")
                and not page.url.startswith("chrome://")
                and not page.is_closed()
            ):
                await self._add_tab_foregrounding_listener(page)
                # logger.debug(f'👁️  Added visibility listener to existing tab: {page.url}')

        return self.session

    async def _add_tab_foregrounding_listener(self, page: Page):
        """
        Attaches listeners that detect when the human steals active tab focus away from the agent.

        Uses a combination of:
        - visibilitychange events
        - window focus/blur events
        - pointermove events

        This multi-method approach provides more reliable detection across browsers.

        TODO: pester the playwright team to add a new event that fires when a headful tab is focused.
        OR implement a browser-use chrome extension that acts as a bridge to the chrome.tabs API.

                        - https://github.com/microsoft/playwright/issues/1290
                        - https://github.com/microsoft/playwright/issues/2286
                        - https://github.com/microsoft/playwright/issues/3570
                        - https://github.com/microsoft/playwright/issues/13989
        """

        def trunc(s, max_len=None):
            s = s.replace("https://", "").replace("http://", "").replace("www.", "")
            if max_len is not None and len(s) > max_len:
                return s[:max_len] + "…"
            return s

        try:
            # Generate a unique function name for this page
            visibility_func_name = f"onVisibilityChange_{id(page)}{id(page.url)}"

            # Define the callback that will be called from browser when tab becomes visible
            async def on_visibility_change(data):
                source = data.get("source", "unknown")

                # Log before and after for debugging
                old_foreground = self.human_current_page
                if old_foreground.url != page.url:
                    logger.warning(
                        f'👁️ Foregound tab changed by human from {trunc(old_foreground.url, 22) if old_foreground else "about:blank"} to {trunc(page.url, 22)} ({source}) but agent will stay on {trunc(self.agent_current_page.url, 22)}'
                    )

                # Update foreground tab
                self.human_current_page = page

            # Expose the function to the browser
            await page.expose_function(visibility_func_name, on_visibility_change)

            # Set up multiple visibility detection methods in the browser
            js_code = """() => {
                // --- Method 1: visibilitychange event (unfortunately *all* tabs are always marked visible by playwright, usually does not fire) ---
                document.addEventListener('visibilitychange', () => {
                    if (document.visibilityState === 'visible') {
                        window.onVisibilityChange_TABID({ source: 'visibilitychange' });
                    }
                });
                
                // --- Method 2: focus/blur events, most reliable method for headful browsers ---
                window.addEventListener('focus', () => {
                    window.onVisibilityChange_TABID({ source: 'focus' });
                });
                
                // --- Method 3: pointermove events (may be fired by agent if we implement AI hover movements) ---
                // Use a throttled handler to avoid excessive calls
                // let lastMove = 0;
                // window.addEventListener('pointermove', () => {
                // 	const now = Date.now();
                // 	if (now - lastMove > 1000) {  // Throttle to once per second
                // 		lastMove = now;
                // 		window.onVisibilityChange_TABID({ source: 'pointermove' });
                // 	}
                // });
            }""".replace(
                "onVisibilityChange_TABID", visibility_func_name
            )
            # multiple reasons for doing it this way ^: stealth, uniqueness, sometimes pageload is cancelled and it runs twice, etc.
            await page.evaluate(js_code)

            # re-add listener to the page for when it navigates to a new url, because previous listeners will be cleared
            page.on("domcontentloaded", self._add_tab_foregrounding_listener)
            logger.debug(f"👀 Added tab focus listeners to tab: {page.url}")

            if page.url != self.agent_current_page.url:
                await on_visibility_change({"source": "navigation"})

        except Exception as e:
            logger.debug(f"Failed to add tab focus listener to {page.url}: {e}")

    async def get_session(self) -> BrowserSession:
        """Lazy initialization of the browser and related components"""
        if self.session is None:
            try:
                return await self._initialize_session()
            except Exception as e:
                logger.error(
                    f"❌  Failed to create new browser session: {e} (did the browser process quit?)"
                )
                raise e
        return self.session

    async def get_current_page(self) -> Page:
        """Legacy method for backwards compatibility, prefer get_agent_current_page()"""
        return await self.get_agent_current_page()

    async def _reconcile_tab_state(self) -> None:
        """Reconcile tab state when tabs might be out of sync.

        This method ensures that:
        1. Both tab references (agent_current_page and human_current_page) are valid
        2. Recovers invalid tab references using valid ones
        3. Handles the case where both references are invalid
        """
        session = await self.get_session()

        agent_tab_valid = (
            self.agent_current_page
            and self.agent_current_page in session.context.pages
            and not self.agent_current_page.is_closed()
        )

        human_current_page_valid = (
            self.human_current_page
            and self.human_current_page in session.context.pages
            and not self.human_current_page.is_closed()
        )

        # Case 1: Both references are valid - nothing to do
        if agent_tab_valid and human_current_page_valid:
            return

        # Case 2: Only agent_current_page is valid - update human_current_page
        if agent_tab_valid and not human_current_page_valid:
            self.human_current_page = self.agent_current_page
            return

        # Case 3: Only human_current_page is valid - update agent_current_page
        if human_current_page_valid and not agent_tab_valid:
            self.agent_current_page = self.human_current_page
            return

        # Case 4: Neither reference is valid - recover from available tabs
        non_extension_pages = [
            page
            for page in session.context.pages
            if not page.url.startswith("chrome-extension://")
            and not page.url.startswith("chrome://")
        ]

        if non_extension_pages:
            # Update both tab references to the most recently opened non-extension page
            recovered_page = non_extension_pages[-1]
            self.agent_current_page = recovered_page
            self.human_current_page = recovered_page
            return

        # Case 5: No valid pages at all - create a new page
        try:
            new_page = await session.context.new_page()
            self.agent_current_page = new_page
            self.human_current_page = new_page
        except Exception:
            # Last resort - recreate the session
            logger.warning("⚠️  No browser window available, recreating session")
            await self._initialize_session()
            if session.context.pages:
                page = session.context.pages[0]
                self.agent_current_page = page
                self.human_current_page = page

    async def _find_and_get_agent_current_page(self) -> Page:
        """Get the page that the agent is currently working with.

        This method prioritizes agent_current_page over human_current_page, ensuring
        that agent operations happen on the intended tab regardless of user
        interaction with the browser.

        If agent_current_page is invalid or closed, it will attempt to recover
        with a valid tab reference by reconciling the tab state.
        """
        session = await self.get_session()

        # First check if agent_current_page is valid
        if (
            self.agent_current_page
            and self.agent_current_page in session.context.pages
            and not self.agent_current_page.is_closed()
        ):
            return self.agent_current_page

        # If we're here, reconcile tab state and try again
        await self._reconcile_tab_state()

        # After reconciliation, agent_current_page should be valid
        if (
            self.agent_current_page
            and self.agent_current_page in session.context.pages
            and not self.agent_current_page.is_closed()
        ):
            return self.agent_current_page

        # If still invalid, fall back to first page method as last resort
        logger.warning(
            "⚠️  Failed to get agent current page, falling back to first page"
        )
        if session.context.pages:
            page = session.context.pages[0]
            self.agent_current_page = page
            self.human_current_page = page
            return page

        # If no pages, create one
        return await session.context.new_page()

    async def get_agent_current_page(self) -> Page:
        page = await self._find_and_get_agent_current_page()
        self.agent_current_page = page
        # update the Animator
        self.animator.page = page
        await page.evaluate(self.animator.animator_script)
        return page

    async def _create_context(self, browser: PlaywrightBrowser):
        """Creates a new browser context with anti-detection measures and loads cookies if available."""
        if (
            self.browser.config.cdp_url
            and len(browser.contexts) > 0
            and not self.config.force_new_context
        ):
            context = browser.contexts[0]
            # For existing contexts, we need to set the viewport size manually
            if context.pages and not self.browser.config.headless:
                for page in context.pages:
                    await self.set_viewport_size(page)
        elif (
            self.browser.config.browser_binary_path
            and len(browser.contexts) > 0
            and not self.config.force_new_context
        ):
            # Connect to existing Chrome instance instead of creating new one
            context = browser.contexts[0]
            # For existing contexts, we need to set the viewport size manually
            if context.pages and not self.browser.config.headless:
                for page in context.pages:
                    await self.set_viewport_size(page)
        else:
            kwargs = {}
            # Set viewport for both headless and non-headless modes
            if self.browser.config.headless:
                # In headless mode, always set viewport and no_viewport=False
                kwargs["viewport"] = {
                    "width": self.config.window_width,
                    "height": self.config.window_height,
                }
                kwargs["no_viewport"] = False
            else:
                # In headful mode, use the no_viewport value from config (defaults to True)
                no_viewport_value = self.config.no_viewport
                kwargs["no_viewport"] = no_viewport_value

                # Only set viewport if no_viewport is False
                if not no_viewport_value:
                    kwargs["viewport"] = {
                        "width": self.config.window_width,
                        "height": self.config.window_height,
                    }

            if self.config.user_agent is not None:
                kwargs["user_agent"] = self.config.user_agent

            context = await browser.new_context(
                **kwargs,
                java_script_enabled=True,
                **(
                    {"bypass_csp": True, "ignore_https_errors": True}
                    if self.config.disable_security
                    else {}
                ),
                record_video_dir=self.config.save_recording_path,
                record_video_size={
                    "width": self.config.window_width,
                    "height": self.config.window_height,
                },
                record_har_path=self.config.save_har_path,
                locale=self.config.locale,
                http_credentials=self.config.http_credentials,
                is_mobile=self.config.is_mobile,
                has_touch=self.config.has_touch,
                geolocation=self.config.geolocation,
                permissions=self.config.permissions,
                timezone_id=self.config.timezone_id,
            )

        # Ensure required permissions are granted
        required_permissions = [
            "clipboard-read",
            "clipboard-write",
        ]  # needed for google sheets automation
        if self.config.geolocation:
            required_permissions.append("geolocation")
        missing_permissions = [
            p for p in required_permissions if p not in self.config.permissions
        ]
        if any(missing_permissions):
            logger.warning(
                f"⚠️ Some permissions required by browser-use {missing_permissions} are missing from BrowserContextConfig(permissions={self.config.permissions}), some features may not work properly!"
            )
        await context.grant_permissions(self.config.permissions)

        if self.config.trace_path:
            await context.tracing.start(screenshots=True, snapshots=True, sources=True)

        # Resize the window for non-headless mode
        if not self.browser.config.headless:
            await self._resize_window(context)

        # Load cookies if they exist
        if self.config.cookies_file and os.path.exists(self.config.cookies_file):
            async with await anyio.open_file(self.config.cookies_file, "r") as f:
                try:
                    cookies = json.loads(await f.read())

                    valid_same_site_values = ["Strict", "Lax", "None"]
                    for cookie in cookies:
                        if "sameSite" in cookie:
                            if cookie["sameSite"] not in valid_same_site_values:
                                logger.warning(
                                    f"Fixed invalid sameSite value '{cookie['sameSite']}' to 'None' for cookie {cookie.get('name')}"
                                )
                                cookie["sameSite"] = "None"
                    logger.info(
                        f"🍪  Loaded {len(cookies)} cookies from {self.config.cookies_file}"
                    )
                    await context.add_cookies(cookies)

                except json.JSONDecodeError as e:
                    logger.error(f"Failed to parse cookies file: {str(e)}")

        init_script = """
            // check to make sure we're not inside the PDF viewer
            window.isPdfViewer = !!document?.body?.querySelector('body > embed[type="application/pdf"][width="100%"]')
            if (!window.isPdfViewer) {
    
                // Permissions
                const originalQuery = window.navigator.permissions.query;
                window.navigator.permissions.query = (parameters) => (
                    parameters.name === 'notifications' ?
                        Promise.resolve({ state: Notification.permission }) :
                        originalQuery(parameters)
                );
                (() => {
                    if (window._eventListenerTrackerInitialized) return;
                    window._eventListenerTrackerInitialized = true;

                    const originalAddEventListener = EventTarget.prototype.addEventListener;
                    const eventListenersMap = new WeakMap();

                    EventTarget.prototype.addEventListener = function(type, listener, options) {
                        if (typeof listener === "function") {
                            let listeners = eventListenersMap.get(this);
                            if (!listeners) {
                                listeners = [];
                                eventListenersMap.set(this, listeners);
                            }

                            listeners.push({
                                type,
                                listener,
                                listenerPreview: listener.toString().slice(0, 100),
                                options
                            });
                        }

                        return originalAddEventListener.call(this, type, listener, options);
                    };

                    window.getEventListenersForNode = (node) => {
                        const listeners = eventListenersMap.get(node) || [];
                        return listeners.map(({ type, listenerPreview, options }) => ({
                            type,
                            listenerPreview,
                            options
                        }));
                    };
                })();
            }
            """

        # Expose anti-detection scripts
        await context.add_init_script(init_script)

        return context

    async def set_viewport_size(self, page: Page) -> None:
        """
        Central method to set viewport size for a page.
        Simple for now, but we may need to add more logic here in the future to rezise surrounding window, change recording options, etc.
        """
        try:
            # Only set viewport size if no_viewport is False (aka viewport=True)
            if self.config.no_viewport is False:
                viewport_size = {
                    "width": self.config.window_width,
                    "height": self.config.window_height,
                }
                await page.set_viewport_size(viewport_size)
                logger.debug(
                    f"Set viewport size to {self.config.window_width}x{self.config.window_height}"
                )
            # else:
            # logger.debug('Skipping viewport size setting because no_viewport is not False')
        except Exception as e:
            logger.debug(f"Failed to set viewport size for page: {e}")

    async def _wait_for_stable_network(self):
        page = await self.get_agent_current_page()

        pending_requests = set()
        last_activity = asyncio.get_event_loop().time()

        # Define relevant resource types and content types
        RELEVANT_RESOURCE_TYPES = {
            "document",
            "stylesheet",
            "image",
            "font",
            "script",
            "iframe",
        }

        RELEVANT_CONTENT_TYPES = {
            "text/html",
            "text/css",
            "application/javascript",
            "image/",
            "font/",
            "application/json",
        }

        # Additional patterns to filter out
        IGNORED_URL_PATTERNS = {
            # Analytics and tracking
            "analytics",
            "tracking",
            "telemetry",
            "beacon",
            "metrics",
            # Ad-related
            "doubleclick",
            "adsystem",
            "adserver",
            "advertising",
            # Social media widgets
            "facebook.com/plugins",
            "platform.twitter",
            "linkedin.com/embed",
            # Live chat and support
            "livechat",
            "zendesk",
            "intercom",
            "crisp.chat",
            "hotjar",
            # Push notifications
            "push-notifications",
            "onesignal",
            "pushwoosh",
            # Background sync/heartbeat
            "heartbeat",
            "ping",
            "alive",
            # WebRTC and streaming
            "webrtc",
            "rtmp://",
            "wss://",
            # Common CDNs for dynamic content
            "cloudfront.net",
            "fastly.net",
        }

        async def on_request(request):
            # Filter by resource type
            if request.resource_type not in RELEVANT_RESOURCE_TYPES:
                return

            # Filter out streaming, websocket, and other real-time requests
            if request.resource_type in {
                "websocket",
                "media",
                "eventsource",
                "manifest",
                "other",
            }:
                return

            # Filter out by URL patterns
            url = request.url.lower()
            if any(pattern in url for pattern in IGNORED_URL_PATTERNS):
                return

            # Filter out data URLs and blob URLs
            if url.startswith(("data:", "blob:")):
                return

            # Filter out requests with certain headers
            headers = request.headers
            if headers.get("purpose") == "prefetch" or headers.get(
                "sec-fetch-dest"
            ) in [
                "video",
                "audio",
            ]:
                return

            nonlocal last_activity
            pending_requests.add(request)
            last_activity = asyncio.get_event_loop().time()
            # logger.debug(f'Request started: {request.url} ({request.resource_type})')

        async def on_response(response):
            request = response.request
            if request not in pending_requests:
                return

            # Filter by content type if available
            content_type = response.headers.get("content-type", "").lower()

            # Skip if content type indicates streaming or real-time data
            if any(
                t in content_type
                for t in [
                    "streaming",
                    "video",
                    "audio",
                    "webm",
                    "mp4",
                    "event-stream",
                    "websocket",
                    "protobuf",
                ]
            ):
                pending_requests.remove(request)
                return

            # Only process relevant content types
            if not any(ct in content_type for ct in RELEVANT_CONTENT_TYPES):
                pending_requests.remove(request)
                return

            # Skip if response is too large (likely not essential for page load)
            content_length = response.headers.get("content-length")
            if content_length and int(content_length) > 5 * 1024 * 1024:  # 5MB
                pending_requests.remove(request)
                return

            nonlocal last_activity
            pending_requests.remove(request)
            last_activity = asyncio.get_event_loop().time()
            # logger.debug(f'Request resolved: {request.url} ({content_type})')

        # Attach event listeners
        page.on("request", on_request)
        page.on("response", on_response)

        try:
            # Wait for idle time
            start_time = asyncio.get_event_loop().time()
            while True:
                await asyncio.sleep(0.1)
                now = asyncio.get_event_loop().time()
                if (
                    len(pending_requests) == 0
                    and (now - last_activity)
                    >= self.config.wait_for_network_idle_page_load_time
                ):
                    break
                if now - start_time > self.config.maximum_wait_page_load_time:
                    logger.debug(
                        f"Network timeout after {self.config.maximum_wait_page_load_time}s with {len(pending_requests)} "
                        f"pending requests: {[r.url for r in pending_requests]}"
                    )
                    break

        finally:
            # Clean up event listeners
            page.remove_listener("request", on_request)
            page.remove_listener("response", on_response)

        logger.debug(
            f"⚖️  Network stabilized for {self.config.wait_for_network_idle_page_load_time} seconds"
        )

    async def _wait_for_dom_stability(
        self,
        timeout: float = 15.0,
        stability_threshold_ms: int = 500,
        long_task_threshold_ms: int = 50,
    ):
        """
        Waits for dynamic page content to stabilize using a multi-signal framework.

        This function injects and runs an advanced JavaScript class ('DynamicContentReady')
        that confirms readiness by observing a combination of signals:
        1. Main Thread Activity (PerformanceObserver for long tasks)
        2. DOM Changes (MutationObserver)
        3. Layout Shifts (ResizeObserver)

        It first programmatically identifies the main content area of the page and
        then waits for that specific area to become stable.

        Args:
            timeout: Maximum time to wait for stability, in seconds.
            stability_threshold_ms: The "quiet period" in milliseconds required for
                                    content and layout to be considered stable.
            long_task_threshold_ms: The duration in milliseconds that qualifies a
                                    browser task as a "long task," indicating a busy
                                    main thread.

        Returns:
            True if the page content stabilizes within the timeout, False otherwise.
        """
        page = await self.get_agent_current_page()
        logger.debug("Starting comprehensive DOM stability wait...")

        # --- The Complete DynamicContentReady JavaScript Framework ---
        # This class is injected into the browser context.
        dcr_framework_script = """
        class DynamicContentReady {
            constructor(options = {}) {
                this.options = {
                    stabilityThreshold: 500,
                    longTaskThreshold: 50,
                    maxWaitTime: 15000,
                    ...options,
                };
                this.state = 'IDLE';
                this.perfObserver = null;
                this.mutObserver = null;
                this.resizeObserver = null;
                this.targetElement = null;
                this.isMainThreadBusy = false;
                this.lastMutationTime = 0;
                this.lastResizeTime = 0;
                this.resolvePromise = null;
                this.rejectPromise = null;
                this.stabilityChecker = null;
                this.timeoutHandle = null;
            }

            waitForReady() {
                if (this.state !== 'IDLE') {
                    return Promise.reject(new Error("DCR is already running."));
                }
                return new Promise((resolve, reject) => {
                    this.resolvePromise = resolve;
                    this.rejectPromise = reject;
                    // Set a master timeout for the whole operation
                    this.timeoutHandle = setTimeout(
                        () => this._fail(`Operation timed out after ${this.options.maxWaitTime}ms`),
                        this.options.maxWaitTime
                    );
                    this._transitionTo('IDENTIFYING');
                });
            }

            _transitionTo(newState) {
                console.log(`DCR State: ${this.state} -> ${newState}`);
                this.state = newState;
                this._onEnterState(newState);
            }

            _onEnterState(state) {
                switch (state) {
                    case 'IDENTIFYING':
                        this.targetElement = this._findBestCandidateElement();
                        if (this.targetElement) {
                            this._transitionTo('MONITORING');
                        } else {
                            this._fail("Could not identify a target content area.");
                        }
                        break;
                    case 'MONITORING':
                        this._setupObservers();
                        this._beginStabilityChecks();
                        break;
                    case 'STABLE':
                        this._cleanup();
                        this.resolvePromise({
                            element: this.targetElement.tagName,
                            reason: "All stability signals achieved."
                        });
                        this._transitionTo('IDLE');
                        break;
                }
            }

            _findBestCandidateElement() {
                let bestCandidate = null;
                let maxScore = -1;
                document.querySelectorAll('body *').forEach(el => {
                    if (this._isElementVisible(el)) {
                        const score = this._calculateElementScore(el);
                        if (score > maxScore) {
                            maxScore = score;
                            bestCandidate = el;
                        }
                    }
                });
                return bestCandidate;
            }

            _calculateElementScore(el) {
                let score = 0;
                const tagName = el.tagName.toUpperCase();
                if (['SCRIPT', 'STYLE', 'NOSCRIPT', 'HEAD', 'META', 'LINK', 'TITLE'].includes(tagName)) return -1;

                if (['MAIN', 'ARTICLE', 'SECTION'].includes(tagName)) score += 20;
                if (['HEADER', 'NAV', 'FOOTER', 'ASIDE'].includes(tagName)) score -= 30;

                const area = el.offsetWidth * el.offsetHeight;
                if (area > 0) {
                     score += Math.log(area + 1) * 2;
                }

                const textLength = el.textContent.trim().length;
                const linkCount = el.querySelectorAll('a').length;
                if (textLength > 100) {
                    score += 15;
                    if (linkCount > 0) {
                        const density = textLength / (linkCount + 1);
                        if (density > 50) score += 10;
                    }
                }
                return score;
            }

            _isElementVisible(el) {
                return !!(el.offsetWidth || el.offsetHeight || el.getClientRects().length);
            }

            _setupObservers() {
                this.lastMutationTime = this.lastResizeTime = Date.now();
                this.isMainThreadBusy = false;

                this.perfObserver = new PerformanceObserver((entryList) => {
                    if (entryList.getEntries().length > 0) {
                        this.isMainThreadBusy = true;
                        setTimeout(() => { this.isMainThreadBusy = false; }, this.options.longTaskThreshold * 1.5);
                    }
                });
                this.perfObserver.observe({ entryTypes: ['longtask'] });

                this.mutObserver = new MutationObserver(() => { this.lastMutationTime = Date.now(); });
                this.mutObserver.observe(this.targetElement, { childList: true, subtree: true, attributes: true, characterData: true });

                this.resizeObserver = new ResizeObserver(() => { this.lastResizeTime = Date.now(); });
                this.resizeObserver.observe(this.targetElement);
            }

            _beginStabilityChecks() {
                this.stabilityChecker = setInterval(() => {
                    const now = Date.now();
                    const isLayoutStable = now - this.lastResizeTime > this.options.stabilityThreshold;
                    const isContentStable = now - this.lastMutationTime > this.options.stabilityThreshold;
                    const isThreadStable = !this.isMainThreadBusy;

                    if (isLayoutStable && isContentStable && isThreadStable) {
                        this._transitionTo('STABLE');
                    }
                }, 100);
            }

            _cleanup() {
                if (this.stabilityChecker) clearInterval(this.stabilityChecker);
                if (this.timeoutHandle) clearTimeout(this.timeoutHandle);
                if (this.perfObserver) this.perfObserver.disconnect();
                if (this.mutObserver) this.mutObserver.disconnect();
                if (this.resizeObserver) this.resizeObserver.disconnect();
            }

            _fail(reason) {
                this._cleanup();
                this.rejectPromise(new Error(reason));
                this._transitionTo('IDLE');
            }
        }
        """

        # Define the JS executor function separately for clarity.
        # This function will be run in the browser's context.
        executor_script = f"""
            async (args) => {{
                {dcr_framework_script}
                const dcr = new DynamicContentReady(args.options);
                try {{
                    const result = await dcr.waitForReady();
                    return {{ stable: true, ...result }};
                }} catch (err) {{
                    return {{ stable: false, reason: err.message }};
                }}
            }}
        """

        try:
            # The argument object to pass to the executor_script.
            script_args = {
                "options": {
                    "stabilityThreshold": stability_threshold_ms,
                    "longTaskThreshold": long_task_threshold_ms,
                    "maxWaitTime": timeout * 1000,
                }
            }

            # Execute the script and pass the arguments.
            result = await page.evaluate(executor_script, script_args)

            if result.get("stable"):
                logger.info(f"✅ DOM is stable. Reason: {result.get('reason')}")
                return True
            else:
                logger.warning(
                    f"⚠️ DOM did not stabilize. Reason: {result.get('reason')}"
                )
                return False

        except Exception as e:
            # This will catch Playwright-level errors (e.g., page closed).
            logger.error(f"An exception occurred during the page.evaluate call: {e}")
            return False

    async def _wait_for_page_and_frames_load(
        self, timeout_overwrite: float | None = None
    ):
        """
        Ensures page is fully loaded before continuing.
        Waits for network to be idle, DOM to stabilize, and enforces minimum wait time.
        Also checks if the loaded URL is allowed.
        """
        # Start timing
        start_time = time.time()

        # Wait for page load
        try:
            await self._wait_for_stable_network()

            # Check if the loaded URL is allowed
            page = await self.get_agent_current_page()

            # FIXME: figure out if we need this here.
            # await page.wait_for_load_state()
            await self._check_and_handle_navigation(page)

            # wait for DOM to stabilize (especially important for JavaScript-heavy sites)
            await self._wait_for_dom_stability(stability_threshold_ms=1000)

        except URLNotAllowedError as e:
            raise e
        except Exception as e:
            logger.warning(f"⚠️  Page load failed: {str(e)}, continuing...")
            pass

        # Calculate remaining time to meet minimum WAIT_TIME
        elapsed = time.time() - start_time
        remaining = max(
            (timeout_overwrite or self.config.minimum_wait_page_load_time) - elapsed, 0
        )

        logger.debug(
            f"--Page loaded in {elapsed:.2f} seconds, waiting for additional {remaining:.2f} seconds"
        )

        # Sleep remaining time if needed
        if remaining > 0:
            await asyncio.sleep(remaining)

    def _is_url_allowed(self, url: str) -> bool:
        """
        Check if a URL is allowed based on the whitelist configuration.

        Supports glob patterns in allowed_domains:
        - *.example.com will match sub.example.com and example.com
        - *google.com will match google.com, agoogle.com, and www.google.com
        """

        if not self.config.allowed_domains:
            return True

        def _show_glob_warning(domain: str, glob: str):
            global _GLOB_WARNING_SHOWN
            if not _GLOB_WARNING_SHOWN:
                logger.warning(
                    # glob patterns are very easy to mess up and match too many domains by accident
                    # e.g. if you only need to access gmail, don't use *.google.com because an attacker could convince the agent to visit a malicious doc
                    # on docs.google.com/s/some/evil/doc to set up a prompt injection attack
                    "⚠️ Allowing agent to visit {domain} based on allowed_domains=['{glob}', ...]. Set allowed_domains=['{domain}', ...] explicitly to avoid the security risks of glob patterns!"
                )
                _GLOB_WARNING_SHOWN = True

        try:
            import fnmatch
            from urllib.parse import urlparse

            parsed_url = urlparse(url)

            # Special case: Allow 'about:blank' explicitly
            if url == "about:blank" or parsed_url.scheme.lower() in (
                "chrome",
                "brave",
                "edge",
                "chrome-extension",
            ):
                return True

            # Extract only the hostname component (without auth credentials or port)
            # Hostname returns only the domain portion, ignoring username:password and port
            domain = parsed_url.hostname.lower() if parsed_url.hostname else ""

            if not domain:
                return False

            for allowed_domain in self.config.allowed_domains:
                allowed_domain = allowed_domain.lower()

                # Handle glob patterns
                if "*" in allowed_domain:
                    # Special handling for *.domain.tld pattern to also match the bare domain
                    if allowed_domain.startswith("*."):
                        # If pattern is *.example.com, also allow example.com (without subdomain)
                        parent_domain = allowed_domain[2:]  # Remove the '*.' prefix
                        if domain == parent_domain or fnmatch.fnmatch(
                            domain, allowed_domain
                        ):
                            _show_glob_warning(domain, allowed_domain)
                            return True
                    else:
                        # For other glob patterns like *google.com
                        if fnmatch.fnmatch(domain, allowed_domain):
                            _show_glob_warning(domain, allowed_domain)
                            return True
                else:
                    # Standard matching (exact or subdomain)
                    if domain == allowed_domain:
                        return True

            return False
        except Exception as e:
            logger.error(f"⛔️  Error checking URL allowlist: {type(e).__name__}: {e}")
            return False

    async def _check_and_handle_navigation(self, page: Page) -> None:
        """Check if current page URL is allowed and handle if not."""
        try:
            # First check if the page is valid - this avoids JS errors
            if page.is_closed():
                logger.warning("Page is closed during navigation check")
                return
                
            # Use try/except when accessing page.url as it could cause JS errors
            try:
                current_url = page.url
            except Exception as e:
                logger.warning(f"Cannot access page URL: {str(e)}")
                return
                
            if not self._is_url_allowed(current_url):
                logger.warning(f"⛔️  Navigation to non-allowed URL detected: {current_url}")
                try:
                    await self.go_back()
                except Exception as e:
                    logger.error(
                        f"⛔️  Failed to go back after detecting non-allowed URL: {str(e)}"
                    )
                raise URLNotAllowedError(f"Navigation to non-allowed URL: {current_url}")
        except Exception as e:
            # Catch any other unexpected errors to prevent them from causing the click to fail
            logger.warning(f"Error in navigation check: {str(e)}")
            # Don't re-raise the exception

    async def navigate_to(self, url: str):
        """Navigate the agent's current tab to a URL"""

        if not self._is_url_allowed(url):
            raise URLNotAllowedError(f"URL not allowed")

        page = await self.get_agent_current_page()
        await page.goto(url)
        await page.wait_for_load_state()

    async def refresh_page(self):
        """Refresh the agent's current page"""
        page = await self.get_agent_current_page()
        await page.reload()
        await page.wait_for_load_state()

    async def go_back(self):
        """Navigate the agent's tab back in browser history"""
        page = await self.get_agent_current_page()
        try:
            # 10 ms timeout
            await page.go_back(timeout=10, wait_until="domcontentloaded")
            # await self._wait_for_page_and_frames_load(timeout_overwrite=1.0)
        except Exception as e:
            # Continue even if its not fully loaded, because we wait later for the page to load
            logger.debug(f"⏮️  Error during go_back: {e}")

    async def go_forward(self):
        """Navigate the agent's tab forward in browser history"""
        page = await self.get_agent_current_page()
        try:
            await page.go_forward(timeout=10, wait_until="domcontentloaded")
        except Exception as e:
            # Continue even if its not fully loaded, because we wait later for the page to load
            logger.debug(f"⏭️  Error during go_forward: {e}")

    async def close_current_tab(self):
        """Close the current tab that the agent is working with.

        This closes the tab that the agent is currently using (agent_current_page),
        not necessarily the tab that is visible to the user (human_current_page).
        If they are the same tab, both references will be updated.
        """
        session = await self.get_session()
        page = await self.get_agent_current_page()

        # Check if this is the foreground tab as well
        is_foreground = page == self.human_current_page

        # Close the tab
        await page.close()

        # Clear agent's reference to the closed tab
        self.agent_current_page = None

        # Clear foreground reference if needed
        if is_foreground:
            self.human_current_page = None

        # Switch to the first available tab if any exist
        if session.context.pages:
            await self.switch_to_tab(0)
            # switch_to_tab already updates both tab references

        # Otherwise, the browser will be closed

    async def get_page_html(self) -> str:
        """Get the HTML content of the agent's current page"""
        page = await self.get_agent_current_page()
        return await page.content()

    async def execute_javascript(self, script: str):
        """Execute JavaScript code on the agent's current page"""
        page = await self.get_agent_current_page()
        return await page.evaluate(script)

    async def get_page_structure(self) -> str:
        """Get a debug view of the page structure including iframes"""
        debug_script = """(() => {
            function getPageStructure(element = document, depth = 0, maxDepth = 10) {
                if (depth >= maxDepth) return '';

                const indent = '  '.repeat(depth);
                let structure = '';

                // Skip certain elements that clutter the output
                const skipTags = new Set(['script', 'style', 'link', 'meta', 'noscript']);

                // Add current element info if it's not the document
                if (element !== document) {
                    const tagName = element.tagName.toLowerCase();

                    // Skip uninteresting elements
                    if (skipTags.has(tagName)) return '';

                    const id = element.id ? `#${element.id}` : '';
                    const classes = element.className && typeof element.className === 'string' ?
                        `.${element.className.split(' ').filter(c => c).join('.')}` : '';

                    // Get additional useful attributes
                    const attrs = [];
                    if (element.getAttribute('role')) attrs.push(`role="${element.getAttribute('role')}"`);
                    if (element.getAttribute('aria-label')) attrs.push(`aria-label="${element.getAttribute('aria-label')}"`);
                    if (element.getAttribute('type')) attrs.push(`type="${element.getAttribute('type')}"`);
                    if (element.getAttribute('name')) attrs.push(`name="${element.getAttribute('name')}"`);
                    if (element.getAttribute('src')) {
                        const src = element.getAttribute('src');
                        attrs.push(`src="${src.substring(0, 50)}${src.length > 50 ? '...' : ''}"`);
                    }

                    // Add element info
                    structure += `${indent}${tagName}${id}${classes}${attrs.length ? ' [' + attrs.join(', ') + ']' : ''}\\n`;

                    // Handle iframes specially
                    if (tagName === 'iframe') {
                        try {
                            const iframeDoc = element.contentDocument || element.contentWindow?.document;
                            if (iframeDoc) {
                                structure += `${indent}  [IFRAME CONTENT]:\\n`;
                                structure += getPageStructure(iframeDoc, depth + 2, maxDepth);
                            } else {
                                structure += `${indent}  [IFRAME: No access - likely cross-origin]\\n`;
                            }
                        } catch (e) {
                            structure += `${indent}  [IFRAME: Access denied - ${e.message}]\\n`;
                        }
                    }
                }

                // Get all child elements
                const children = element.children || element.childNodes;
                for (const child of children) {
                    if (child.nodeType === 1) { // Element nodes only
                        structure += getPageStructure(child, depth + 1, maxDepth);
                    }
                }

                return structure;
            }

            return getPageStructure();
        })()"""

        page = await self.get_agent_current_page()
        structure = await page.evaluate(debug_script)
        return structure

    @time_execution_sync(
        "--get_state"
    )  # This decorator might need to be updated to handle async
    async def get_state(self, cache_clickable_elements_hashes: bool) -> BrowserState:
        """Get the current state of the browser

        cache_clickable_elements_hashes: bool
                If True, cache the clickable elements hashes for the current state. This is used to calculate which elements are new to the llm (from last message) -> reduces token usage.
        """
        await self._wait_for_page_and_frames_load()
        session = await self.get_session()
        updated_state = await self._get_updated_state()

        # Find out which elements are new
        # Do this only if url has not changed
        if cache_clickable_elements_hashes:
            # if we are on the same url as the last state, we can use the cached hashes
            if (
                session.cached_state_clickable_elements_hashes
                and session.cached_state_clickable_elements_hashes.url
                == updated_state.url
            ):
                # Pointers, feel free to edit in place
                updated_state_clickable_elements = (
                    ClickableElementProcessor.get_clickable_elements(
                        updated_state.element_tree
                    )
                )

                for dom_element in updated_state_clickable_elements:
                    dom_element.is_new = (
                        ClickableElementProcessor.hash_dom_element(dom_element)
                        not in session.cached_state_clickable_elements_hashes.hashes  # see which elements are new from the last state where we cached the hashes
                    )
            # in any case, we need to cache the new hashes
            session.cached_state_clickable_elements_hashes = (
                CachedStateClickableElementsHashes(
                    url=updated_state.url,
                    hashes=ClickableElementProcessor.get_clickable_elements_hashes(
                        updated_state.element_tree
                    ),
                )
            )

        session.cached_state = updated_state

        # Save cookies if a file is specified
        if self.config.cookies_file:
            asyncio.create_task(self.save_cookies())

        return session.cached_state

    async def _get_updated_state(self, focus_element: int = -1) -> BrowserState:
        """Update and return state."""
        session = await self.get_session()

        # Check if current page is still valid, if not switch to another available page
        try:
            page = await self.get_agent_current_page()
            # Test if page is still accessible
            await page.evaluate("1")
        except Exception as e:
            logger.debug(f"👋  Current page is no longer accessible: {str(e)}")
            raise BrowserError("Browser closed: no valid pages available")

        try:
            await self.remove_highlights()
            dom_service = DomService(page)

            content = await dom_service.get_clickable_elements(
                focus_element=focus_element,
                viewport_expansion=self.config.viewport_expansion,
                highlight_elements=self.config.highlight_elements,
            )

            tabs_info = await self.get_tabs_info()

            # Get all cross-origin iframes within the page and open them in new tabs
            # mark the titles of the new tabs so the LLM knows to check them for additional content
            # unfortunately too buggy for now, too many sites use invisible cross-origin iframes for ads, tracking, youtube videos, social media, etc.
            # and it distracts the bot by opening a lot of new tabs
            # iframe_urls = await dom_service.get_cross_origin_iframes()
            # for url in iframe_urls:
            # 	if url in [tab.url for tab in tabs_info]:
            # 		continue  # skip if the iframe if we already have it open in a tab
            # 	new_page_id = tabs_info[-1].page_id + 1
            # 	logger.debug(f'Opening cross-origin iframe in new tab #{new_page_id}: {url}')
            # 	await self.create_new_tab(url)
            # 	tabs_info.append(
            # 		TabInfo(
            # 			page_id=new_page_id,
            # 			url=url,
            # 			title=f'iFrame opened as new tab, treat as if embedded inside page #{self.state.target_id}: {page.url}',
            # 			parent_page_id=self.state.target_id,
            # 		)
            # 	)

            screenshot_b64 = await self.take_screenshot()
            pixels_above, pixels_below = await self.get_scroll_info(page)

            # Find the agent's active tab ID
            agent_current_page_id = 0
            if self.agent_current_page:
                for tab_info in tabs_info:
                    if tab_info.url == self.agent_current_page.url:
                        agent_current_page_id = tab_info.page_id
                        break

            self.current_state = BrowserState(
                element_tree=content.element_tree,
                selector_map=content.selector_map,
                url=page.url,
                title=await page.title(),
                tabs=tabs_info,
                screenshot=screenshot_b64,
                pixels_above=pixels_above,
                pixels_below=pixels_below,
            )

            return self.current_state
        except Exception as e:
            logger.error(f"❌  Failed to update state: {str(e)}")
            # Return last known good state if available
            if hasattr(self, "current_state"):
                return self.current_state
            raise

    # region - Browser Actions
    @time_execution_async("--take_screenshot")
    async def take_screenshot(self, full_page: bool = False) -> str:
        """
        Returns a base64 encoded screenshot of the current page.
        """
        page = await self.get_agent_current_page()

        # We no longer force tabs to the foreground  it disrupts user focus
        # await page.bring_to_front()
        
        await self.animator.hide_animations()
        
        screenshot = await page.screenshot(
            full_page=full_page,
            animations="disabled",
            caret="initial",
        )

        asyncio.create_task(self.animator.show_animations())
        asyncio.create_task(self.animator.screenshot())

        screenshot_b64 = base64.b64encode(screenshot).decode("utf-8")

        # await self.remove_highlights()

        return screenshot_b64

    @time_execution_async("--remove_highlights")
    async def remove_highlights(self):
        """
        Removes all highlight overlays and labels created by the highlightElement function.
        Handles cases where the page might be closed or inaccessible.
        """
        try:
            page = await self.get_agent_current_page()
            await page.evaluate(
                """
                try {
                    // Remove the highlight container and all its contents
                    const container = document.getElementById('playwright-highlight-container');
                    if (container) {
                        container.remove();
                    }

                    // Remove highlight attributes from elements
                    const highlightedElements = document.querySelectorAll('[browser-user-highlight-id^="playwright-highlight-"]');
                    highlightedElements.forEach(el => {
                        el.removeAttribute('browser-user-highlight-id');
                    });
                } catch (e) {
                    console.error('Failed to remove highlights:', e);
                }
                """
            )
        except Exception as e:
            logger.debug(
                f"⚠  Failed to remove highlights (this is usually ok): {str(e)}"
            )
            # Don't raise the error since this is not critical functionality
            pass

    # endregion

    # region - User Actions

    @classmethod
    def _convert_simple_xpath_to_css_selector(cls, xpath: str) -> str:
        """Converts simple XPath expressions to CSS selectors."""
        if not xpath:
            return ""

        # Remove leading slash if present
        xpath = xpath.lstrip("/")

        # Split into parts
        parts = xpath.split("/")
        css_parts = []

        for part in parts:
            if not part:
                continue

            # Handle custom elements with colons by escaping them
            if ":" in part and "[" not in part:
                base_part = part.replace(":", r"\:")
                css_parts.append(base_part)
                continue

            # Handle index notation [n]
            if "[" in part:
                base_part = part[: part.find("[")]
                # Handle custom elements with colons in the base part
                if ":" in base_part:
                    base_part = base_part.replace(":", r"\:")
                index_part = part[part.find("[") :]

                # Handle multiple indices
                indices = [i.strip("[]") for i in index_part.split("]")[:-1]]

                for idx in indices:
                    try:
                        # Handle numeric indices
                        if idx.isdigit():
                            index = int(idx) - 1
                            base_part += f":nth-of-type({index + 1})"
                        # Handle last() function
                        elif idx == "last()":
                            base_part += ":last-of-type"
                        # Handle position() functions
                        elif "position()" in idx:
                            if ">1" in idx:
                                base_part += ":nth-of-type(n+2)"
                    except ValueError:
                        continue

                css_parts.append(base_part)
            else:
                css_parts.append(part)

        base_selector = " > ".join(css_parts)
        return base_selector

    @classmethod
    @time_execution_sync("--enhanced_css_selector_for_element")
    def _enhanced_css_selector_for_element(
        cls, element: DOMElementNode, include_dynamic_attributes: bool = True
    ) -> str:
        """
        Creates a CSS selector for a DOM element, handling various edge cases and special characters.

        Args:
                        element: The DOM element to create a selector for

        Returns:
                        A valid CSS selector string
        """
        try:
            # Get base selector from XPath
            css_selector = cls._convert_simple_xpath_to_css_selector(element.xpath)

            # Handle class attributes
            if (
                "class" in element.attributes
                and element.attributes["class"]
                and include_dynamic_attributes
            ):
                # Define a regex pattern for valid class names in CSS
                valid_class_name_pattern = re.compile(r"^[a-zA-Z_][a-zA-Z0-9_-]*$")

                # Iterate through the class attribute values
                classes = element.attributes["class"].split()
                for class_name in classes:
                    # Skip empty class names
                    if not class_name.strip():
                        continue

                    # Check if the class name is valid
                    if valid_class_name_pattern.match(class_name):
                        # Append the valid class name to the CSS selector
                        css_selector += f".{class_name}"
                    else:
                        # Skip invalid class names
                        continue

            # Expanded set of safe attributes that are stable and useful for selection
            SAFE_ATTRIBUTES = {
                # Data attributes (if they're stable in your application)
                "id",
                # Standard HTML attributes
                "name",
                "type",
                "placeholder",
                # Accessibility attributes
                "aria-label",
                "aria-labelledby",
                "aria-describedby",
                "role",
                # Common form attributes
                "for",
                "autocomplete",
                "required",
                "readonly",
                # Media attributes
                "alt",
                "title",
                "src",
                # Custom stable attributes (add any application-specific ones)
                "href",
                "target",
            }

            if include_dynamic_attributes:
                dynamic_attributes = {
                    "data-id",
                    "data-qa",
                    "data-cy",
                    "data-testid",
                }
                SAFE_ATTRIBUTES.update(dynamic_attributes)

            # Handle other attributes
            for attribute, value in element.attributes.items():
                if attribute == "class":
                    continue

                # Skip invalid attribute names
                if not attribute.strip():
                    continue

                if attribute not in SAFE_ATTRIBUTES:
                    continue

                # Escape special characters in attribute names
                safe_attribute = attribute.replace(":", r"\:")

                # Handle different value cases
                if value == "":
                    css_selector += f"[{safe_attribute}]"
                elif any(char in value for char in "\"'<>`\n\r\t"):
                    # Use contains for values with special characters
                    # For newline-containing text, only use the part before the newline
                    if "\n" in value:
                        value = value.split("\n")[0]
                    # Regex-substitute *any* whitespace with a single space, then strip.
                    collapsed_value = re.sub(r"\s+", " ", value).strip()
                    # Escape embedded double-quotes.
                    safe_value = collapsed_value.replace('"', '\\"')
                    css_selector += f'[{safe_attribute}*="{safe_value}"]'
                else:
                    css_selector += f'[{safe_attribute}="{value}"]'

            return css_selector

        except Exception:
            # Fallback to a more basic selector if something goes wrong
            tag_name = element.tag_name or "*"
            return f"{tag_name}[highlight_index='{element.highlight_index}']"

    @time_execution_async("--is_visible")
    async def _is_visible(self, element: ElementHandle) -> bool:
        """
        Checks if an element is visible on the page.
        We use our own implementation instead of relying solely on Playwright's is_visible() because
        of edge cases with CSS frameworks like Tailwind. When elements use Tailwind's 'hidden' class,
        the computed style may return display as '' (empty string) instead of 'none', causing Playwright
        to incorrectly consider hidden elements as visible. By additionally checking the bounding box
        dimensions, we catch elements that have zero width/height regardless of how they were hidden.
        """
        is_hidden = await element.is_hidden()
        bbox = await element.bounding_box()

        return (
            not is_hidden
            and bbox is not None
            and bbox["width"] > 0
            and bbox["height"] > 0
        )

    @time_execution_async("--get_locate_element")
    async def get_locate_element(self, element: DOMElementNode) -> ElementHandle | None:
        current_frame = await self.get_agent_current_page()

        # Start with the target element and collect all parents
        parents: list[DOMElementNode] = []
        current = element
        while current.parent is not None:
            parent = current.parent
            parents.append(parent)
            current = parent

        # Reverse the parents list to process from top to bottom
        parents.reverse()

        # Process all iframe parents in sequence
        iframes = [item for item in parents if item.tag_name == "iframe"]
        for parent in iframes:
            css_selector = self._enhanced_css_selector_for_element(
                parent,
                include_dynamic_attributes=self.config.include_dynamic_attributes,
            )
            current_frame = current_frame.frame_locator(css_selector)

        css_selector = self._enhanced_css_selector_for_element(
            element, include_dynamic_attributes=self.config.include_dynamic_attributes
        )

        try:
            if isinstance(current_frame, FrameLocator):
                element_handle = await current_frame.locator(
                    css_selector
                ).element_handle()
                return element_handle
            else:
                # Try to scroll into view if hidden
                element_handle = await current_frame.query_selector(css_selector)
                if element_handle:
                    is_visible = await self._is_visible(element_handle)
                    if is_visible:
                        await element_handle.scroll_into_view_if_needed()
                    return element_handle
                return None
        except Exception as e:
            logger.error(f"❌  Failed to locate element: {str(e)}")
            return None

    @time_execution_async("--get_locate_element_by_xpath")
    async def get_locate_element_by_xpath(self, xpath: str) -> ElementHandle | None:
        """
        Locates an element on the page using the provided XPath.
        """
        current_frame = await self.get_agent_current_page()

        try:
            # Use XPath to locate the element
            element_handle = await current_frame.query_selector(f"xpath={xpath}")
            if element_handle:
                is_visible = await self._is_visible(element_handle)
                if is_visible:
                    await element_handle.scroll_into_view_if_needed()
                return element_handle
            return None
        except Exception as e:
            logger.error(f"❌  Failed to locate element by XPath {xpath}: {str(e)}")
            return None

    @time_execution_async("--get_locate_element_by_css_selector")
    async def get_locate_element_by_css_selector(
        self, css_selector: str
    ) -> ElementHandle | None:
        """
        Locates an element on the page using the provided CSS selector.
        """
        current_frame = await self.get_agent_current_page()

        try:
            # Use CSS selector to locate the element
            element_handle = await current_frame.query_selector(css_selector)
            if element_handle:
                is_visible = await self._is_visible(element_handle)
                if is_visible:
                    await element_handle.scroll_into_view_if_needed()
                return element_handle
            return None
        except Exception as e:
            logger.error(
                f"❌  Failed to locate element by CSS selector {css_selector}: {str(e)}"
            )
            return None

    @time_execution_async("--get_locate_element_by_text")
    async def get_locate_element_by_text(
        self, text: str, nth: int | None = 0, element_type: str | None = None
    ) -> ElementHandle | None:
        """
        Locates an element on the page using the provided text.
        If `nth` is provided, it returns the nth matching element (0-based).
        If `element_type` is provided, filters by tag name (e.g., 'button', 'span').
        """
        current_frame = await self.get_agent_current_page()
        try:
            # handle also specific element type or use any type.
            selector = f'{element_type or "*"}:text("{text}")'
            elements = await current_frame.query_selector_all(selector)
            # considering only visible elements
            elements = [el for el in elements if await self._is_visible(el)]

            if not elements:
                logger.error(f"No visible element with text '{text}' found.")
                return None

            if nth is not None:
                if 0 <= nth < len(elements):
                    element_handle = elements[nth]
                else:
                    logger.error(
                        f"Visible element with text '{text}' not found at index {nth}."
                    )
                    return None
            else:
                element_handle = elements[0]

            is_visible = await self._is_visible(element_handle)
            if is_visible:
                await element_handle.scroll_into_view_if_needed()
            return element_handle
        except Exception as e:
            logger.error(f"❌  Failed to locate element by text '{text}': {str(e)}")
            return None

    @time_execution_async("--input_text_element_node")
    async def _input_text_element_node(self, element_node: DOMElementNode, text: str):
        """
        Input text into an element with proper error handling and state management.
        Handles different types of input fields and ensures proper element state before input.
        """
        try:
            element_handle = await self.get_locate_element(element_node)

            if element_handle is None:
                raise BrowserError(
                    f"Element '{element_node.get_description()}' not found"
                )

            try:
                await element_handle.wait_for_element_state("stable", timeout=1000)
                is_visible = await self._is_visible(element_handle)
                if is_visible:
                    await element_handle.scroll_into_view_if_needed(timeout=1000)
            except Exception:
                pass

            try:
                # Preferred: Playwright's fill() on the element handle
                # FIXME: Test this .fill() as its performing clicks on incorrect positions.
                await element_handle.fill(text)
                logger.info(f"Filled text '{text}' into element: {element_node.get_description()}")
                
            except Exception:
                # Fallback: Manual select-all and backspace
                asyncio.create_task(self.animator.type(element_node=element_node))
                page: Page = await self.get_agent_current_page()

                await element_handle.click()  # Ensure focus
                if await page.evaluate("navigator.platform.includes('Mac')"):
                    await page.keyboard.press("Meta+A")
                else:
                    await page.keyboard.press("Control+A")
                await page.keyboard.press("Backspace")

                await page.keyboard.type(text)

        except Exception as e:
            raise BrowserError(e)

    @time_execution_async("--click_element_node")
    async def _click_element_node(self, element_node: DOMElementNode) -> str | None:
        """
        Optimized method to click an element using xpath.
        """
        asyncio.create_task(self.animator.click(element_node=element_node))

        page = await self.get_agent_current_page()

        try:
            element_handle = await self.get_locate_element(element_node)

            if element_handle is None:
                raise Exception(f"Element: {repr(element_node)} not found")

            async def perform_click(click_func):
                """Performs the actual click, handling both download
                and navigation scenarios."""
                if self.config.save_downloads_path:
                    try:
                        # Try short-timeout expect_download to detect a file download has been been triggered
                        async with page.expect_download(timeout=5000) as download_info:
                            await click_func()
                        download = await download_info.value
                        # Determine file path
                        suggested_filename = download.suggested_filename
                        unique_filename = await self._get_unique_filename(
                            self.config.save_downloads_path, suggested_filename
                        )
                        download_path = os.path.join(
                            self.config.save_downloads_path, unique_filename
                        )
                        await download.save_as(download_path)
                        logger.debug(
                            f"⬇️  Download triggered. Saved file to: {download_path}"
                        )
                        return download_path
                    except TimeoutError:
                        # If no download is triggered, treat as normal click
                        logger.debug(
                            "No download triggered within timeout. Checking navigation..."
                        )
                        await page.wait_for_load_state()
                        await self._check_and_handle_navigation(page)
                else:
                    # Standard click logic if no download is expected
                    await click_func()
                    await page.wait_for_load_state()
                    await self._check_and_handle_navigation(page)

            try:
                # TODO: use the playwright locator to click which will wait, handle enable, stable etc.
                return await perform_click(lambda: element_handle.click(timeout=200))
            except URLNotAllowedError as e:
                raise e
            except Exception:
                try:
                    return await perform_click(
                        lambda: page.evaluate("(el) => el.click()", element_handle)
                    )
                except URLNotAllowedError as e:
                    raise e
                except Exception as e:
                    raise Exception(f"Failed to click element: {str(e)}")

        except URLNotAllowedError as e:
            raise e
        except Exception as e:
            raise Exception(
                f"Failed to click element: {repr(element_node)}. Error: {str(e)}"
            )

    async def is_element_dropdown(
        self,
        element_node: DOMElementNode,
        interactive: bool = False,
        search_children: bool = True,
    ) -> dict | str | None:
        """
        Comprehensive dropdown detection. Returns a dictionary with dropdown details or None.
        """

        page = await self.get_agent_current_page()
        result = {
            "is_dropdown": False,
            "dropdown_type": None,
            "detection_method": None,
            "target_xpath": None,
            "original_xpath": element_node.xpath,
        }

        # ---------- Static analysis ----------
        tag = element_node.tag_name.lower()
        attrs = {k.lower(): v for k, v in element_node.attributes.items()}

        if tag == "select":
            logger.debug("Detected native dropdown through static analysis")
            result.update(
                {
                    "is_dropdown": True,
                    "dropdown_type": "native",
                    "detection_method": "static",
                    "target_xpath": element_node.xpath,
                }
            )
            return result

        if any(
            attr in attrs.get("role", "").lower() for attr in ["combobox", "listbox", "menu"]
        ):
            logger.debug("Detected custom dropdown through role attribute")
            result.update(
                {
                    "is_dropdown": True,
                    "dropdown_type": "custom",
                    "detection_method": "static",
                    "target_xpath": element_node.xpath,
                }
            )
            return result

        if any(
            cls in attrs.get("class", "").lower()
            for cls in [
                "dropdown",
                "select",
                "combobox",
                "menu-button",
                "select-button",
            ]
        ):
            logger.debug("Detected custom dropdown through class attribute")
            result.update(
                {
                    "is_dropdown": True,
                    "dropdown_type": "custom",
                    "detection_method": "static",
                    "target_xpath": element_node.xpath,
                }
            )
            return result

        if any(
            attr in element_node.attributes
            for attr in ["aria-haspopup", "aria-expanded", "aria-controls"]
        ):
            logger.debug("Detected custom dropdown through ARIA attribute")
            result.update(
                {
                    "is_dropdown": True,
                    "dropdown_type": "custom",
                    "detection_method": "static",
                    "target_xpath": element_node.xpath,
                }
            )
            return result

        # If neither interactive nor child searching requested, return early
        if not interactive and not search_children:
            return result

        # Reusable JS snippets (kept as constants to avoid duplication)
        VISIBLE_DROPDOWN_QUERY_JS = """() => {
            return Array.from(document.querySelectorAll('ul[role="listbox"], [role="menu"], .dropdown-menu, ul.options, .select-options'))
                .filter(el => {
                    const style = window.getComputedStyle(el);
                    return style.display !== 'none' && style.visibility !== 'hidden';
                })
                .map(el => el.outerHTML);
        }"""

        CHILD_SEARCH_JS = """(xpath) => {
            const el = document.evaluate(xpath, document, null,
                XPathResult.FIRST_ORDERED_NODE_TYPE, null).singleNodeValue;
            if (!el) return null;
            
            const getXPath = function(element) {
                if (element.id) {
                    return `//*[@id="${element.id}"]`;
                }
                
                let path = [];
                while (element && element.nodeType === Node.ELEMENT_NODE) {
                    let idx = 0;
                    for (let sibling = element.previousSibling; sibling; sibling = sibling.previousSibling) {
                        if (sibling.nodeType === Node.DOCUMENT_TYPE_NODE) continue;
                        if (sibling.nodeName === element.nodeName) idx++;
                    }
                    path.unshift(`${element.nodeName.toLowerCase()}[${idx+1}]`);
                    element = element.parentNode;
                }
                return path.length ? '/' + path.join('/') : '';
            };
            
            // First check direct children (fastest)
            const directSelect = el.querySelector('select');
            if (directSelect) {
                return {
                    type: 'native',
                    xpath: getXPath(directSelect),
                    method: 'child-direct'
                };
            }
            
            const directCustom = el.querySelector('[role="combobox"], [role="listbox"], [role="menu"], .dropdown, .select, .combobox, .dropdown-toggle, .menu-button, .select-button, [aria-haspopup], [aria-expanded], [aria-controls]');
            if (directCustom) {
                return {
                    type: 'custom',
                    xpath: getXPath(directCustom),
                    method: 'child-direct'
                };
            }
            
            // Bounded BFS search (limited depth)
            let queue = Array.from(el.children);
            let visited = 0;
            const MAX_NODES = 30;
            const MAX_DEPTH = 2;
            
            for (let depth = 0; depth < MAX_DEPTH && queue.length > 0 && visited < MAX_NODES; depth++) {
                const levelSize = queue.length;
                for (let i = 0; i < levelSize && visited < MAX_NODES; i++) {
                    visited++;
                    const node = queue.shift();
                    
                    if (node.tagName === 'SELECT') {
                        return {
                            type: 'native',
                            xpath: getXPath(node),
                            method: 'child-search'
                        };
                    }
                    
                    if (node.getAttribute('role') === 'combobox' ||
                        node.getAttribute('role') === 'listbox' ||
                        node.getAttribute('role') === 'menu' ||
                        node.classList.contains('dropdown') ||
                        node.classList.contains('select') ||
                        node.classList.contains('combobox') ||
                        node.classList.contains('dropdown-toggle') ||
                        node.classList.contains('menu-button') ||
                        node.classList.contains('select-button') ||
                        node.hasAttribute('aria-haspopup') ||
                        node.hasAttribute('aria-expanded') ||
                        node.hasAttribute('aria-controls')) {
                        return {
                            type: 'custom',
                            xpath: getXPath(node),
                            method: 'child-search'
                        };
                    }
                    
                    Array.from(node.children).forEach(child => queue.push(child));
                }
            }
            
            return null;
        }"""

        try:
            element_handle = await self.get_locate_element(element_node)
            if not element_handle:
                logger.debug("Could not locate element for dropdown detection")
                return result

            # ---------- Interactive checks (click/ARIA/keyboard) ----------
            if interactive:
                try:
                    pre_click_visible = await page.evaluate(VISIBLE_DROPDOWN_QUERY_JS)

                    # Try clicking the element
                    try:
                        await element_handle.click(timeout=1000, force=True)
                        await page.wait_for_timeout(500)
                    except Exception as click_exc:
                        logger.debug(
                            f"Click attempt threw exception (may still continue): {str(click_exc)}"
                        )

                    post_click_visible = await page.evaluate(VISIBLE_DROPDOWN_QUERY_JS)
                    new_elements = [
                        el for el in post_click_visible if el not in pre_click_visible
                    ]
                    if new_elements:
                        logger.debug("Detected dropdown through click interaction")
                        result.update(
                            {
                                "is_dropdown": True,
                                "dropdown_type": "custom",
                                "detection_method": "click",
                                "target_xpath": element_node.xpath,
                            }
                        )
                        return result

                    # Check aria-expanded attribute changed to true
                    try:
                        is_expanded = await page.evaluate(
                            """(xpath) => {
                                const el = document.evaluate(xpath, document, null,
                                    XPathResult.FIRST_ORDERED_NODE_TYPE, null).singleNodeValue;
                                return el && el.getAttribute('aria-expanded') === 'true';
                            }""",
                            element_node.xpath,
                        )
                        if is_expanded:
                            logger.debug(
                                "Detected dropdown through aria-expanded change"
                            )
                            result.update(
                                {
                                    "is_dropdown": True,
                                    "dropdown_type": "custom",
                                    "detection_method": "click",
                                    "target_xpath": element_node.xpath,
                                }
                            )
                            return result
                    except Exception as e:
                        logger.debug(f"aria-expanded check failed: {str(e)}")

                    # Keyboard interactions (accessibility)
                    try:
                        await element_handle.focus()

                        # Enter
                        await page.keyboard.press("Enter")
                        await page.wait_for_timeout(300)
                        post_key_visible = await page.evaluate(
                            VISIBLE_DROPDOWN_QUERY_JS
                        )
                        new_elements_key = [
                            el for el in post_key_visible if el not in pre_click_visible
                        ]
                        if new_elements_key:
                            logger.debug(
                                "Detected dropdown through keyboard Enter interaction"
                            )
                            result.update(
                                {
                                    "is_dropdown": True,
                                    "dropdown_type": "custom",
                                    "detection_method": "keyboard-enter",
                                    "target_xpath": element_node.xpath,
                                }
                            )
                            return result

                        # ArrowDown
                        await element_handle.focus()
                        await page.keyboard.press("ArrowDown")
                        await page.wait_for_timeout(300)
                        post_arrow_visible = await page.evaluate(
                            VISIBLE_DROPDOWN_QUERY_JS
                        )
                        new_elements_arrow = [
                            el
                            for el in post_arrow_visible
                            if el not in pre_click_visible
                        ]
                        if new_elements_arrow:
                            logger.debug(
                                "Detected dropdown through keyboard ArrowDown interaction"
                            )
                            result.update(
                                {
                                    "is_dropdown": True,
                                    "dropdown_type": "custom",
                                    "detection_method": "keyboard-arrow",
                                    "target_xpath": element_node.xpath,
                                }
                            )
                            return result

                    except Exception as ke:
                        logger.debug(f"Keyboard detection attempt failed: {str(ke)}")

                except Exception as e:
                    logger.debug(
                        f"Click/interactive detection attempt failed: {str(e)}"
                    )

            # ---------- Child search (non-interactive or fallback) ----------
            if search_children:
                try:
                    dropdown_search = await page.evaluate(
                        CHILD_SEARCH_JS, element_node.xpath
                    )
                    if dropdown_search:
                        logger.debug(
                            f"Found dropdown element within target: {dropdown_search}"
                        )
                        result.update(
                            {
                                "is_dropdown": True,
                                "dropdown_type": dropdown_search.get("type"),
                                "detection_method": dropdown_search.get("method"),
                                "target_xpath": dropdown_search.get("xpath"),
                            }
                        )
                        return result
                except Exception as e:
                    logger.debug(f"Child search detection failed: {str(e)}")

        except Exception as e:
            logger.error(f"Error during dropdown detection: {str(e)}")

        # If we reach here, no dropdown was detected
        return result

    async def get_dropdown_details(self, element_node: DOMElementNode) -> dict | None:
        """
        Gets comprehensive details about a dropdown element including type, options, and summary.
        First robustly detects if the element is or contains a dropdown,
        then opens it like a user would and extracts its options.
        """
        page = await self.get_agent_current_page()

        # First use our robust detection method
        dropdown_detection = await self.is_element_dropdown(
            element_node, interactive=True, search_children=True
        )
        if not dropdown_detection["is_dropdown"]:
            logger.debug(f"No dropdown detected for element {element_node.tag_name}")
            return None

        # We found a dropdown, but it might be a child element
        dropdown_type = dropdown_detection["dropdown_type"]
        target_xpath = dropdown_detection["target_xpath"]

        # If we detected a dropdown in a child element, get that element
        target_element = element_node
        if target_xpath and target_xpath != element_node.xpath:
            # Create a new element node for the target
            dom_item = await page.evaluate(
                """(xpath) => {
                const el = document.evaluate(xpath, document, null,
                    XPathResult.FIRST_ORDERED_NODE_TYPE, null).singleNodeValue;
                if (!el) return null;
                
                return {
                    xpath,
                    tag_name: el.tagName,
                    attributes: Object.fromEntries(
                        Array.from(el.attributes).map(attr => [attr.name, attr.value])
                    ),
                    text_content: el.textContent
                };
            }""",
                target_xpath,
            )

            if dom_item:
                # Create new DOMElementNode with the found element's data
                target_element = DOMElementNode(
                    xpath=target_xpath,
                    tag_name=dom_item["tag_name"],
                    attributes=dom_item["attributes"],
                    text_content=dom_item.get("text_content", ""),
                    children=[],  # We don't need children for this operation
                )
                logger.debug(
                    f"Using detected dropdown element: {target_element.tag_name}"
                )
            else:
                logger.debug(
                    f"Could not get target element at {target_xpath}, using original"
                )
                # Continue with original element

        try:
            # For custom dropdowns, try to open it first
            if dropdown_type == "custom":
                dropdown_label = "Custom dropdown"
                dropdown_data = await self._get_custom_dropdown_options(
                    target_element, page
                )
            else:  # native dropdown
                # Native dropdowns don't need to be explicitly opened to read options
                dropdown_label = "Native dropdown"
                dropdown_data = await self._get_native_dropdown_options(
                    target_element, page
                )

                # But we might still try to open it if we got no options
                if not dropdown_data.get("options"):
                    open_info = await self._open_dropdown(target_element, page)
                    # Try to get options again if opened
                    if open_info.get("opened"):
                        dropdown_data = await self._get_native_dropdown_options(
                            target_element, page
                        )
                        # Add opening method from the open_info
                        dropdown_data["opened_by"] = open_info.get("method")

            # Format options and create summary
            raw_options = dropdown_data.get("options", [])
            formatted_result = self._format_dropdown_options_and_summary(
                raw_options, dropdown_label
            )

            # Extract selected options in dict format
            selected_options = []
            for opt in raw_options:
                if opt.get("selected"):
                    selected_options.append(
                        {
                            "index": opt.get("index"),
                            "text": opt.get("text", ""),
                            "value": opt.get("value", ""),
                        }
                    )

            # Add selected options to the result
            formatted_result["selected_options"] = selected_options

            # Add dropdown type and all metadata to the result
            formatted_result["dropdown_type"] = dropdown_type
            formatted_result["opened"] = bool(dropdown_data.get("opened_by"))
            formatted_result["opened_by"] = dropdown_data.get("opened_by")
            formatted_result["frame_name"] = dropdown_data.get("frame_name")
            formatted_result["frame_index"] = dropdown_data.get("frame_index")
            formatted_result["index_base"] = dropdown_data.get("index_base", 0)

            # Add detection metadata
            formatted_result["detection_method"] = dropdown_detection[
                "detection_method"
            ]
            formatted_result["original_xpath"] = dropdown_detection["original_xpath"]
            formatted_result["target_xpath"] = dropdown_detection["target_xpath"]

            return formatted_result

        except Exception as e:
            logger.error(f"Failed to process {dropdown_type} dropdown: {str(e)}")
            return {
                "dropdown_type": dropdown_type,
                "options": [],
                "selected_options": [],  # Empty array for selected options
                "summary": f"{dropdown_type.title()} dropdown detected but error occurred: {str(e)}",
                "opened": False,
                "opened_by": None,
                "frame_name": None,
                "frame_index": None,
                "index_base": 0,
                "detection_method": dropdown_detection["detection_method"],
                "original_xpath": dropdown_detection["original_xpath"],
                "target_xpath": dropdown_detection["target_xpath"],
            }

    async def select_dropdown_option_by_index(
        self, element_node: DOMElementNode, option_index: int
    ) -> dict:
        """
        Selects an option from a dropdown by its index.

        Args:
            element_node: The DOM node of the dropdown element
            option_index: The index of the option to select (0-based)

        Returns:
            dict: Dictionary with selection results
                {
                    "success": bool,       # Whether the selection was successful
                    "message": str,        # Status message or error
                    "selected_option": dict, # Information about the selected option
                }
        """
        page = await self.get_agent_current_page()
        result = {
            "success": False,
            "message": "Failed to select option",
            "selected_option": None,
        }

        try:
            # First, check if this is a dropdown
            dropdown_info = await self.is_element_dropdown(element_node)
            if not dropdown_info.get("is_dropdown", False):
                result["message"] = "Element is not a dropdown"
                return result

            # Get dropdown type and target element if different
            dropdown_type = dropdown_info["dropdown_type"]
            target_xpath = dropdown_info.get("target_xpath") or element_node.xpath

            # For native dropdowns, get the options to validate the index
            target_option = None
            if dropdown_type == "native":
                # Get options data to find our target option
                dropdown_data = await self._get_native_dropdown_options(
                    element_node, page
                )
                options = dropdown_data.get("options", [])

                if not options:
                    result["message"] = "No options found in native dropdown"
                    return result

                # Make sure the index is within range
                if option_index < 0 or option_index >= len(options):
                    result["message"] = (
                        f"Option index {option_index} out of range (0-{len(options)-1})"
                    )
                    return result

                target_option = options[option_index]

            # For native <select> dropdowns
            if dropdown_type == "native":
                for frame_index, frame in enumerate(page.frames):
                    try:
                        success = await frame.evaluate(
                            """
                            (args) => {
                                const select = document.evaluate(args.xpath, document, null,
                                    XPathResult.FIRST_ORDERED_NODE_TYPE, null).singleNodeValue;
                                if (!select) return false;
                                
                                // Set the select value
                                select.selectedIndex = args.optionIndex;
                                
                                // Trigger change event
                                const event = new Event('change', { bubbles: true });
                                select.dispatchEvent(event);
                                
                                // Also dispatch input event for good measure
                                const inputEvent = new Event('input', { bubbles: true });
                                select.dispatchEvent(inputEvent);
                                
                                return true;
                            }
                            """,
                            {"xpath": target_xpath, "optionIndex": option_index},
                        )

                        if success:
                            result["success"] = True
                            result["message"] = (
                                f"Successfully selected option at index {option_index}"
                            )
                            result["selected_option"] = target_option
                            return result

                    except Exception as e:
                        logger.debug(f"Error in frame {frame_index}: {str(e)}")

            # For custom dropdowns, we need to click to open it first
            else:
                logger.debug(
                    f"Handling custom dropdown selection for index {option_index}"
                )
                # First locate and click the dropdown to open it
                element_handle = await self.get_locate_element(element_node)
                await element_handle.click()
                await asyncio.sleep(0.5)  # Wait for dropdown to open

                # Try to find the option and click it
                open_info = await self._open_dropdown(element_node, page)

                if open_info.get("opened"):
                    logger.debug(
                        f"Dropdown opened successfully via {open_info.get('method')}"
                    )

                    # Get all visible dropdown options using more comprehensive selectors
                    try:
                        # First, get all options to validate our index is in range
                        options_data = await page.evaluate(
                            """
                            () => {
                                // Comprehensive selectors for dropdown options
                                const OPTION_SELECTORS = [
                                    'li', 
                                    '[role="option"]', 
                                    '[role="menuitem"]', 
                                    '.dropdown-item', 
                                    '.select-option',
                                    '.menu-item',
                                    '.option', 
                                    '.item',
                                    '.select-item',
                                    'div[id^="item-"]'
                                ].join(', ');
                                
                                // Look for visible options
                                const options = Array.from(document.querySelectorAll(OPTION_SELECTORS))
                                    .filter(el => {
                                        // Check if element is visible
                                        const style = window.getComputedStyle(el);
                                        return el.offsetParent !== null && 
                                               style.display !== 'none' && 
                                               style.visibility !== 'hidden' &&
                                               style.opacity !== '0';
                                    })
                                    .map((el, index) => ({
                                        text: el.textContent.trim(),
                                        index: index
                                    }));
                                
                                return { options };
                            }
                            """
                        )

                        visible_options = options_data.get("options", [])

                        logger.debug(
                            f"Found {len(visible_options)} visible dropdown options"
                        )

                        if not visible_options:
                            result["message"] = (
                                "No visible dropdown options found after opening dropdown"
                            )
                            return result

                        # Make sure the index is within range
                        if option_index < 0 or option_index >= len(visible_options):
                            result["message"] = (
                                f"Option index {option_index} out of range (0-{len(visible_options)-1})"
                            )
                            return result

                        # Now click the option at the specified index
                        target_option = visible_options[option_index]

                        # Try to click the option at the given index
                        success = await page.evaluate(
                            """
                            (args) => {
                                // Comprehensive selectors for dropdown options
                                const OPTION_SELECTORS = [
                                    'li', 
                                    '[role="option"]', 
                                    '[role="menuitem"]', 
                                    '.dropdown-item', 
                                    '.select-option',
                                    '.menu-item',
                                    '.option', 
                                    '.item',
                                    '.select-item',
                                    'div[id^="item-"]'
                                ].join(', ');
                                
                                // Get all visible options
                                const options = Array.from(document.querySelectorAll(OPTION_SELECTORS))
                                    .filter(el => {
                                        // Check if element is visible
                                        const style = window.getComputedStyle(el);
                                        return el.offsetParent !== null && 
                                               style.display !== 'none' && 
                                               style.visibility !== 'hidden' &&
                                               style.opacity !== '0';
                                    });
                                
                                if (options.length === 0) return false;
                                
                                // Check if index is in range
                                if (args.optionIndex >= 0 && args.optionIndex < options.length) {
                                    // Get the element at the index
                                    const option = options[args.optionIndex];
                                    console.log('Clicking option:', option.textContent);
                                    
                                    // Click the option
                                    option.click();
                                    return true;
                                }
                                
                                return false;
                            }
                            """,
                            {"optionIndex": option_index},
                        )

                        if success:
                            result["success"] = True
                            result["message"] = (
                                f"Successfully clicked option at index {option_index}"
                            )
                            result["selected_option"] = target_option
                            return result
                    except Exception as e:
                        logger.debug(
                            f"Error selecting custom dropdown option: {str(e)}"
                        )

            result["message"] = (
                "Failed to select option - could not interact with dropdown"
            )
            return result

        except Exception as e:
            result["message"] = f"Error: {str(e)}"
            logger.error(f"Error in select_dropdown_option_by_index: {str(e)}")
            return result

    async def _get_native_dropdown_options(self, element_node, page) -> dict:
        """
        Gets options from a native <select> dropdown.

        Returns:
            dict: Dictionary with options and metadata about the dropdown
                {
                    "options": list,       # List of options with text, value, index
                    "frame_name": str,     # Name of the frame containing the dropdown
                    "frame_index": int,    # Index of the frame containing the dropdown
                    "index_base": int      # Base index for dropdown options (usually 0 or 1)
                }
        """
        result = {
            "options": [],
            "frame_name": None,
            "frame_index": None,
            "index_base": 0,  # Native <select> dropdowns are 0-indexed
        }

        for frame_index, frame in enumerate(page.frames):
            try:
                options_data = await frame.evaluate(
                    """
                    (xpath) => {
                        const select = document.evaluate(xpath, document, null,
                            XPathResult.FIRST_ORDERED_NODE_TYPE, null).singleNodeValue;
                        if (!select) return null;
                        
                        // Check if it's a 1-indexed dropdown (some frameworks start from 1)
                        // This is a heuristic - if the first option has index 1, it's likely 1-indexed
                        const indexBase = select.options.length > 0 && select.options[0].index === 1 ? 1 : 0;
                        
                        return {
                            options: Array.from(select.options).map(opt => ({
                                text: opt.text,
                                value: opt.value,
                                index: opt.index,
                                selected: opt.selected,
                                disabled: opt.disabled
                            })),
                            indexBase: indexBase
                        };
                    }
                    """,
                    element_node.xpath,
                )

                if options_data and options_data.get("options"):
                    logger.debug(f"Found dropdown in frame {frame_index}")
                    result["options"] = options_data["options"]
                    result["frame_index"] = frame_index
                    result["frame_name"] = frame.name or frame.url
                    result["index_base"] = options_data.get("indexBase", 0)
                    return result

            except Exception as frame_e:
                logger.debug(f"Frame {frame_index} evaluation failed: {str(frame_e)}")

        # If we reach here, we didn't find the dropdown in any frame
        logger.debug("Dropdown not found in any frame")
        return result

    def _format_dropdown_options_and_summary(self, raw_options, dropdown_label) -> dict:
        """
        Formats dropdown options and creates a summary.

        Args:
            raw_options: Can be a list of options directly, or a dict with "options" key
            dropdown_label: Label for the dropdown type (e.g., "Native dropdown")

        Returns:
            dict: Dictionary with formatted options and summary
        """
        # Handle case where raw_options might be a dict from the new implementation
        options_list = (
            raw_options.get("options") if isinstance(raw_options, dict) else raw_options
        )
        options_list = options_list or []

        option_count = len(options_list)
        selected_count = sum(1 for opt in options_list if opt.get("selected"))

        # Convert options to simplified string format
        formatted_options = []
        for opt in options_list:
            status_parts = []
            if opt.get("selected"):
                status_parts.append("selected")
            if opt.get("disabled", False):
                status_parts.append("disabled")

            status = f" ({', '.join(status_parts)})" if status_parts else ""

            # Format: "index: value (text) status"
            # If value is empty or same as text, just use text
            index = opt.get("index", 0)
            text = opt.get("text", "")
            value = opt.get("value", "")

            if not value or value == text:
                formatted_options.append(f"{index}: {text}{status}")
            else:
                formatted_options.append(f"{index}: {value} ({text}){status}")

        # Create a summary with sample options
        summary_parts = [f"{dropdown_label} with {option_count} options"]
        if selected_count > 0:
            summary_parts[0] += f" ({selected_count} selected)"

        # Add sample options to the summary if there are any options
        if option_count > 0:
            # Create sample of options to show
            sample_options = self._select_sample_options(
                options_list, formatted_options
            )

            # Add samples to summary
            if sample_options:
                if option_count > 5:
                    summary_parts.append(
                        f"Sample options ({len(sample_options)} of {option_count}):"
                    )
                else:
                    summary_parts.append("Options:")
                summary_parts.append("\n".join(sample_options))

        # Create the result
        result = {"options": formatted_options, "summary": "\n".join(summary_parts)}

        # Add any additional metadata from the raw_options if it's a dict
        if isinstance(raw_options, dict):
            # Add any metadata fields except 'options' which we've already handled
            for key, value in raw_options.items():
                if key != "options" and key not in result:
                    result[key] = value

        return result

    def _select_sample_options(self, raw_options, formatted_options) -> list[str]:
        """
        Selects a representative sample of options to display in the summary.
        """
        option_count = len(raw_options)

        # Get selected options first in the sample
        selected_indices = [
            i for i, opt in enumerate(raw_options) if opt.get("selected")
        ]
        sample_indices = selected_indices[:3]  # Take up to 3 selected options

        # Add more options to sample if needed (up to 5 total)
        remaining_slots = 5 - len(sample_indices)
        if remaining_slots > 0:
            # Get indices that aren't already in the sample
            other_indices = [i for i in range(option_count) if i not in sample_indices]

            # Take a few from the beginning, middle, and end if there are many
            if len(other_indices) > remaining_slots and len(other_indices) > 6:
                middle_idx = len(other_indices) // 2
                sample_indices.extend(
                    [
                        *other_indices[: remaining_slots // 2],  # Beginning
                        *other_indices[middle_idx : middle_idx + 1],  # Middle
                        *other_indices[-remaining_slots // 2 :],  # End
                    ][:remaining_slots]
                )  # Ensure we don't exceed
            else:
                # Just take the first few if not that many
                sample_indices.extend(other_indices[:remaining_slots])

        # Sort the indices to present them in order
        sample_indices.sort()

        # Collect sample options
        return [formatted_options[i] for i in sample_indices]

    async def _is_dropdown_expanded(self, page, xpath) -> dict:
        """
        Helper method to check if a dropdown is expanded.

        Args:
            page (Page): Playwright page
            xpath (str): XPath to the dropdown trigger element

        Returns:
            dict: Information about the dropdown expansion state
                {
                    "expanded": bool,  # Whether the dropdown is expanded
                    "by": str | None,  # What indicates it's expanded (aria, class, visible-container)
                }
        """
        try:
            return await page.evaluate(
                """
                (xpath) => {
                    const el = document.evaluate(xpath, document, null, 
                        XPathResult.FIRST_ORDERED_NODE_TYPE, null).singleNodeValue;
                    if (!el) return {expanded: false};
                    
                    // Check if aria-expanded changed
                    if (el.getAttribute('aria-expanded') === 'true') {
                        return {expanded: true, by: 'aria'};
                    }
                    
                    // Check for expanded classes
                    if (el.classList.contains('expanded') || 
                        el.classList.contains('open') || 
                        el.classList.contains('active')) {
                        return {expanded: true, by: 'class'};
                    }
                    
                    // Check if any dropdown menu is now visible
                    const possibleContainers = [
                        el.nextElementSibling,
                        ...Array.from(el.parentElement.querySelectorAll('ul.dropdown-menu, [role="listbox"], [role="menu"]')),
                        ...Array.from(document.querySelectorAll(`[aria-labelledby="${el.id}"]`))
                    ].filter(Boolean);
                    
                    for (const container of possibleContainers) {
                        const style = window.getComputedStyle(container);
                        if (style.display !== 'none' && style.visibility !== 'hidden') {
                            return {
                                expanded: true, 
                                by: 'visible-container'
                            };
                        }
                    }
                    
                    return {expanded: false};
                }
            """,
                xpath,
            )
        except Exception as e:
            logger.debug(f"Error checking dropdown expansion state: {str(e)}")
            return {"expanded": False}

    async def _open_dropdown(self, element_node, page) -> dict:
        """
        Opens a dropdown like a real user would, by trying multiple interaction methods.
        """

        result = {
            "opened": False,
            "method": None,
            "frame_name": None,
            "frame_index": None,
        }

        try:
            # Get element handle and frame info
            element_handle = await self.get_locate_element(element_node)
            if not element_handle:
                logger.debug("Could not locate element for dropdown opening")
                return result

            # Get frame info
            try:
                # More careful handling of frame name to avoid function object errors
                frame_name = None

                # First try to safely get frame name
                if hasattr(page, "frame"):
                    if hasattr(page.frame, "name"):
                        try:
                            # Check if it's a callable or a property
                            if callable(page.frame.name):
                                # It's a method, don't call it
                                frame_name = (
                                    page.frame.url
                                    if hasattr(page.frame, "url")
                                    else None
                                )
                            else:
                                # It's a property
                                frame_name = page.frame.name
                        except Exception:
                            # Fall back to URL if name access fails
                            if hasattr(page.frame, "url"):
                                frame_name = page.frame.url
                    elif hasattr(page.frame, "url"):
                        frame_name = page.frame.url

                result["frame_name"] = frame_name

                # Get frame index
                if hasattr(page, "frames") and hasattr(page, "frame"):
                    try:
                        for i, frame in enumerate(page.frames):
                            if frame == page.frame:
                                result["frame_index"] = i
                                break
                    except Exception:
                        pass
            except Exception as e:
                logger.debug(f"Error getting frame info: {str(e)}")

            # First check if dropdown is already expanded
            expand_check_result = await self._is_dropdown_expanded(
                page, element_node.xpath
            )

            if expand_check_result.get("expanded"):
                logger.debug("Dropdown appears to be already expanded")
                result["opened"] = True
                result["method"] = "already-open"
                return result

            # Strategy 1: Try clicking the element (most natural user interaction)
            logger.debug("Attempting to open dropdown by clicking")
            try:
                await element_handle.click(timeout=1000)
                await asyncio.sleep(
                    0.5
                )  # Longer pause to ensure animations/scripts complete

                # Check if dropdown is now expanded using our helper method
                expand_result = await self._is_dropdown_expanded(
                    page, element_node.xpath
                )

                if expand_result.get("expanded"):
                    logger.debug(
                        f"Successfully opened dropdown by clicking, detected by: {expand_result.get('by')}"
                    )
                    result["opened"] = True
                    result["method"] = "click"

                    return result
            except Exception as e:
                logger.debug(f"Click method failed to open dropdown: {str(e)}")

            # Strategy 2: Try keyboard interaction (for accessibility-compliant dropdowns)
            logger.debug("Attempting to open dropdown with keyboard")
            try:
                # Focus the element first
                await element_handle.focus()

                # Try pressing Enter (common for buttons/dropdowns)
                await page.keyboard.press("Enter")
                await asyncio.sleep(0.1)

                # Check if it worked using our helper method
                expand_result = await self._is_dropdown_expanded(
                    page, element_node.xpath
                )

                if expand_result.get("expanded"):
                    logger.debug("Successfully opened dropdown with Enter key")
                    result["opened"] = True
                    result["method"] = "keyboard-enter"
                    return result

                # Try arrow down (common for selects and comboboxes)
                await page.keyboard.press("ArrowDown")
                await asyncio.sleep(0.1)

                expand_result = await self._is_dropdown_expanded(
                    page, element_node.xpath
                )

                if expand_result.get("expanded"):
                    logger.debug("Successfully opened dropdown with ArrowDown key")
                    result["opened"] = True
                    result["method"] = "keyboard-arrowdown"
                    return result

                # Try space key (also common for buttons)
                await page.keyboard.press(" ")
                await asyncio.sleep(0.1)

                expand_result = await self._is_dropdown_expanded(
                    page, element_node.xpath
                )

                if expand_result.get("expanded"):
                    logger.debug("Successfully opened dropdown with Space key")
                    result["opened"] = True
                    result["method"] = "keyboard-space"
                    return result
            except Exception as e:
                logger.debug(f"Keyboard methods failed to open dropdown: {str(e)}")

            # Strategy 3: Fall back to attribute modification (least reliable but worth trying)
            logger.debug("Attempting to open dropdown by setting aria-expanded")
            try:
                # Set aria-expanded attribute directly
                await page.evaluate(
                    """(xpath) => {
                    const el = document.evaluate(xpath, document, null, 
                        XPathResult.FIRST_ORDERED_NODE_TYPE, null).singleNodeValue;
                    if (el) el.setAttribute('aria-expanded', 'true');
                }""",
                    element_node.xpath,
                )

                await asyncio.sleep(0.1)  # Brief pause to let any scripts react

                # Check if setting the attribute worked using our helper method
                expand_result = await self._is_dropdown_expanded(
                    page, element_node.xpath
                )

                if expand_result.get("expanded"):
                    logger.debug("Successfully opened dropdown by setting attribute")
                    result["opened"] = True
                    result["method"] = "attribute"
                    return result
            except Exception as e:
                logger.debug(f"Attribute method failed to open dropdown: {str(e)}")

            logger.debug("All methods failed to open dropdown")
            return result

        except Exception as e:
            logger.error(f"Error while trying to open dropdown: {str(e)}")
            return result

    async def _get_custom_dropdown_options(self, element_node, page):
        """
        Helper method to detect options in custom dropdowns.
        First tries to open the dropdown like a user would, then extracts options.

        Args:
            element_node (DOMElementNode): The dropdown trigger element
            page (Page): Playwright page

        Returns:
            dict: Dictionary with options and metadata about the dropdown
                {
                    "options": list,       # List of options with text, value, index
                    "opened_by": str,      # Method used to open the dropdown
                    "frame_name": str,     # Name of the frame containing the dropdown
                    "frame_index": int,    # Index of the frame containing the dropdown
                    "index_base": int      # Base index for dropdown options (usually 0)
                }
        """
        try:
            # First attempt to open the dropdown like a real user would
            dropdown_info = await self._open_dropdown(element_node, page)

            result = {
                "options": [],
                "opened_by": dropdown_info.get("method"),
                "frame_name": dropdown_info.get("frame_name"),
                "frame_index": dropdown_info.get("frame_index"),
                "index_base": 0,  # Most custom dropdowns are 0-indexed
            }

            # Extract options from the dropdown
            # In your Python function, replace container_script string with the following
            container_script = """
                (triggerXPath) => {
                    // Constants (single source of truth)
                    const OPTION_SELECTORS = 'li, [role="option"], [role="menuitem"], .dropdown-item, .option, .select-option, .menu-item, div[id^="item-"]';
                    const CLICKABLE_FALLBACK = 'div[tabindex="0"], button, a';
                    const CONTAINER_SELECTORS = '[role="listbox"], [role="menu"], [role="list"], ul.dropdown-menu, ul.options, .select-options, .dropdown-list';
                    const TOLERANCE = 100;

                    // Helpers
                    const isVisible = (el) => {
                        if (!el) return false;
                        const style = window.getComputedStyle(el);
                        if (style.display === 'none' || style.visibility === 'hidden' || style.opacity === '0') return false;
                        const rect = el.getBoundingClientRect();
                        return rect.width > 0 && rect.height > 0;
                    };

                    const mapOptions = (nodes) => {
                        return Array.from(nodes).map((opt, idx) => {
                            const text = (opt.textContent || '').trim();
                            const value = opt.getAttribute('data-value') || opt.getAttribute('value') || opt.getAttribute('data-option') || opt.id || text;
                            const selected = (opt.getAttribute && opt.getAttribute('aria-selected') === 'true') ||
                                             opt.classList.contains('selected') ||
                                             opt.classList.contains('active') ||
                                             opt.getAttribute('aria-checked') === 'true';
                            return { text, value, index: idx, selected: !!selected };
                        });
                    };

                    const extractOptionsFromContainer = (container) => {
                        if (!container) return [];
                        // Try canonical option selectors
                        let optionElements = container.querySelectorAll(OPTION_SELECTORS);
                        if (optionElements && optionElements.length) return mapOptions(optionElements);

                        // Fallback to clickable elements inside container
                        let clickable = container.querySelectorAll(CLICKABLE_FALLBACK);
                        if (clickable && clickable.length) return mapOptions(clickable);

                        return [];
                    };

                    // Start: find trigger
                    const triggerElement = document.evaluate(triggerXPath, document, null, XPathResult.FIRST_ORDERED_NODE_TYPE, null).singleNodeValue;
                    if (!triggerElement) return [];

                    // Use a Set to collect unique candidate containers
                    const candidateSet = new Set();

                    // Strategy A: aria-controls -> element by id
                    if (triggerElement.hasAttribute && triggerElement.hasAttribute('aria-controls')) {
                        const controlsId = triggerElement.getAttribute('aria-controls');
                        if (controlsId) {
                            const ctl = document.getElementById(controlsId);
                            if (ctl) candidateSet.add(ctl);
                        }
                    }

                    // Strategy B: sibling(s) of trigger (fast)
                    let sibling = triggerElement.nextElementSibling;
                    while (sibling) {
                        candidateSet.add(sibling);
                        sibling = sibling.nextElementSibling;
                    }
                    sibling = triggerElement.previousElementSibling;
                    while (sibling) {
                        candidateSet.add(sibling);
                        sibling = sibling.previousElementSibling;
                    }

                    // Strategy C: containers inside parent and parent's siblings
                    const parent = triggerElement.parentElement;
                    if (parent) {
                        // direct children containers
                        const parentContainers = parent.querySelectorAll(CONTAINER_SELECTORS);
                        parentContainers.forEach(el => candidateSet.add(el));

                        // parent's sibling containers (if any)
                        const grandParent = parent.parentElement;
                        if (grandParent) {
                            Array.from(grandParent.children).forEach(sib => {
                                if (sib !== parent) {
                                    const sibContainers = sib.querySelectorAll(CONTAINER_SELECTORS);
                                    sibContainers.forEach(el => candidateSet.add(el));
                                }
                            });
                        }
                    }

                    // Strategy D: related containers via attributes (data-parent-id, aria-labelledby, aria-controls referencing trigger id)
                    if (triggerElement.id) {
                        const related = document.querySelectorAll(`[aria-labelledby="${triggerElement.id}"], [aria-controls="${triggerElement.id}"], [data-parent-id="${triggerElement.id}"], [data-target="${triggerElement.id}"]`);
                        related.forEach(el => candidateSet.add(el));
                    }
                    if (triggerElement.dataset && triggerElement.dataset.id) {
                        const related2 = document.querySelectorAll(`[data-parent-id="${triggerElement.dataset.id}"], [data-target="${triggerElement.dataset.id}"]`);
                        related2.forEach(el => candidateSet.add(el));
                    }

                    // Evaluate candidates quickly (prefer ones that are visible and produce options)
                    for (const container of candidateSet) {
                        try {
                            if (!container) continue;
                            if (!isVisible(container)) continue;
                            const options = extractOptionsFromContainer(container);
                            if (options && options.length) return options;
                        } catch (err) {
                            // ignore and continue
                        }
                    }

                    // Strategy E: broader but filtered search - visible containers near trigger
                    const triggerRect = triggerElement.getBoundingClientRect();
                    const allPotential = Array.from(document.querySelectorAll(CONTAINER_SELECTORS));
                    const visibleNearby = allPotential.filter(container => {
                        if (!isVisible(container)) return false;
                        const rect = container.getBoundingClientRect();
                        const below = rect.top >= triggerRect.bottom - TOLERANCE;
                        const horizontallyAligned = (rect.left >= triggerRect.left - TOLERANCE && rect.left <= triggerRect.right + TOLERANCE) ||
                                                    (rect.right >= triggerRect.left - TOLERANCE && rect.right <= triggerRect.right + TOLERANCE);
                        return below && horizontallyAligned;
                    });

                    for (const container of visibleNearby) {
                        const options = extractOptionsFromContainer(container);
                        if (options && options.length) return options;
                    }

                    // Final fallback: visible option-like elements (position filtered)
                    const allVisibleItems = Array.from(document.querySelectorAll(OPTION_SELECTORS)).filter(el => {
                        if (!isVisible(el)) return false;
                        const rect = el.getBoundingClientRect();
                        const isBelow = rect.top >= triggerRect.bottom - TOLERANCE;
                        const isNotTrigger = el !== triggerElement;
                        return isBelow && isNotTrigger;
                    });

                    if (allVisibleItems && allVisibleItems.length) return mapOptions(allVisibleItems);

                    return [];
                }
                """

            options = await page.evaluate(container_script, element_node.xpath)

            result["options"] = options or []
            return result

        except Exception as e:
            logger.error(f"Error detecting custom dropdown options: {str(e)}")
            return {
                "options": [],
                "opened_by": None,
                "frame_name": None,
                "frame_index": None,
                "index_base": 0,
            }

    @time_execution_async("--get_tabs_info")
    async def get_tabs_info(self) -> list[TabInfo]:
        """Get information about all tabs"""
        session = await self.get_session()

        tabs_info = []
        for page_id, page in enumerate(session.context.pages):
            try:
                tab_info = TabInfo(
                    page_id=page_id,
                    url=page.url,
                    title=await asyncio.wait_for(page.title(), timeout=1),
                )
            except TimeoutError:
                # page.title() can hang forever on tabs that are crashed/disappeared/about:blank
                # we dont want to try automating those tabs because they will hang the whole script
                logger.debug(
                    "⚠  Failed to get tab info for tab #%s: %s (ignoring)",
                    page_id,
                    page.url,
                )
                tab_info = TabInfo(
                    page_id=page_id,
                    url="about:blank",
                    title="ignore this tab and do not use it",
                )
            tabs_info.append(tab_info)

        return tabs_info

    @time_execution_async("--switch_to_tab")
    async def switch_to_tab(self, page_id: int) -> None:
        """Switch to a specific tab by its page_id"""
        session = await self.get_session()
        pages = session.context.pages

        if page_id >= len(pages):
            raise BrowserError(f"No tab found with page_id: {page_id}")

        page = pages[page_id]

        # Check if the tab's URL is allowed before switching
        if not self._is_url_allowed(page.url):
            raise BrowserError(f"Cannot switch to tab with non-allowed URL: {page.url}")

        # Update target ID if using CDP
        if self.browser.config.cdp_url:
            targets = await self._get_cdp_targets()
            for target in targets:
                if target["url"] == page.url:
                    self.state.target_id = target["targetId"]
                    break

        # Update both tab references - agent wants this tab, and it's now in the foreground
        self.agent_current_page = page
        self.human_current_page = page

        # Bring tab to front and wait for it to load
        await page.bring_to_front()
        await page.wait_for_load_state()

        # Set the viewport size for the tab
        await self.set_viewport_size(page)

    @time_execution_async("--create_new_tab")
    async def create_new_tab(self, url: str | None = None) -> None:
        """Create a new tab and optionally navigate to a URL"""
        if url and not self._is_url_allowed(url):
            raise BrowserError(f"URL is blocked")

        session = await self.get_session()
        new_page = await session.context.new_page()

        # Update both tab references - agent wants this tab, and it's now in the foreground
        self.agent_current_page = new_page
        self.human_current_page = new_page

        await new_page.wait_for_load_state()

        # Set the viewport size for the new tab
        await self.set_viewport_size(new_page)

        if url:
            await new_page.goto(url)
            await self._wait_for_page_and_frames_load(timeout_overwrite=1)

        # Get target ID for new page if using CDP
        if self.browser.config.cdp_url:
            targets = await self._get_cdp_targets()
            for target in targets:
                if target["url"] == new_page.url:
                    self.state.target_id = target["targetId"]
                    break

    # region - Helper methods for easier access to the DOM

    async def get_selector_map(self) -> SelectorMap:
        session = await self.get_session()
        if session.cached_state is None:
            return {}
        return session.cached_state.selector_map

    async def get_element_by_index(self, index: int) -> ElementHandle | None:
        selector_map = await self.get_selector_map()
        element_handle = await self.get_locate_element(selector_map[index])
        return element_handle

    async def get_dom_element_by_index(self, index: int) -> DOMElementNode:
        if not index:
            return None
        selector_map = await self.get_selector_map()
        try:
            value = selector_map[index]
        except KeyError:
            return None
        return value

    async def save_cookies(self):
        """Save current cookies to file"""
        if self.session and self.session.context and self.config.cookies_file:
            try:
                cookies = await self.session.context.cookies()
                logger.debug(
                    f"🍪  Saving {len(cookies)} cookies to {self.config.cookies_file}"
                )

                # Check if the path is a directory and create it if necessary
                dirname = os.path.dirname(self.config.cookies_file)
                if dirname:
                    os.makedirs(dirname, exist_ok=True)

                async with await anyio.open_file(self.config.cookies_file, "w") as f:
                    await f.write(json.dumps(cookies))
            except Exception as e:
                logger.warning(f"❌  Failed to save cookies: {str(e)}")

    async def is_text_field_focused(self, page: "Page") -> bool:
        """
        Checks if a text field element is currently focused in the browser.

        This uses document.activeElement and checks if the element is a text input field
        like input[type="text"], textarea, contenteditable, or other editable fields.

        Args:
            page: The current Playwright page to check

        Returns:
            bool: True if a text field is focused, False otherwise
        """
        if not page:
            return False

        try:
            # Execute JavaScript to check if a text field is focused
            is_focused = await page.evaluate(
                """() => {
                const active = document.activeElement;
                if (!active) return false;
                
                // Check if it's an input field that accepts text
                if (active.tagName === 'INPUT') {
                    const type = active.getAttribute('type') || 'text';
                    return ['text', 'email', 'password', 'search', 'tel', 'url', 'number'].includes(type.toLowerCase());
                }
                
                // Check if it's a textarea
                if (active.tagName === 'TEXTAREA') return true;
                
                // Check if it's contenteditable
                if (active.getAttribute('contenteditable') === 'true') return true;
                
                // Check for rich text editors with design mode
                if (document.designMode === 'on') return true;
                
                return false;
            }"""
            )

            return bool(is_focused)
        except Exception as e:
            logger.error(f"Error checking if text field is focused: {e}")
            return False

    async def is_file_uploader(
        self, element_node: DOMElementNode, max_depth: int = 3, current_depth: int = 0
    ) -> bool:
        """Check if element or its children are file uploaders"""
        if current_depth > max_depth:
            return False

        # Check current element
        is_uploader = False

        if not isinstance(element_node, DOMElementNode):
            return False

        # Check for file input attributes
        if element_node.tag_name == "input":
            is_uploader = (
                element_node.attributes.get("type") == "file"
                or element_node.attributes.get("accept") is not None
            )

        if is_uploader:
            return True

        # Recursively check children
        if element_node.children and current_depth < max_depth:
            for child in element_node.children:
                if isinstance(child, DOMElementNode):
                    if await self.is_file_uploader(child, max_depth, current_depth + 1):
                        return True

        return False

    async def get_scroll_info(self, page: Page) -> tuple[int, int]:
        """Get scroll position information for the current page."""
        scroll_y = await page.evaluate("window.scrollY")
        viewport_height = await page.evaluate("window.innerHeight")
        total_height = await page.evaluate("document.documentElement.scrollHeight")
        pixels_above = scroll_y
        pixels_below = total_height - (scroll_y + viewport_height)
        return pixels_above, pixels_below

    async def reset_context(self):
        """Reset the browser session
        Call this when you don't want to kill the context but just kill the state
        """
        # close all tabs and clear cached state
        session = await self.get_session()

        pages = session.context.pages
        for page in pages:
            await page.close()

        session.cached_state = None
        self.state.target_id = None

    async def _get_unique_filename(self, directory, filename):
        """Generate a unique filename by appending (1), (2), etc., if a file already exists."""
        base, ext = os.path.splitext(filename)
        counter = 1
        new_filename = filename
        while os.path.exists(os.path.join(directory, new_filename)):
            new_filename = f"{base} ({counter}){ext}"
            counter += 1
        return new_filename

    async def _get_cdp_targets(self) -> list[dict]:
        """Get all CDP targets directly using CDP protocol"""
        if not self.browser.config.cdp_url or not self.session:
            return []

        try:
            pages = self.session.context.pages
            if not pages:
                return []

            cdp_session = await pages[0].context.new_cdp_session(pages[0])
            result = await cdp_session.send("Target.getTargets")
            await cdp_session.detach()
            return result.get("targetInfos", [])
        except Exception as e:
            logger.debug(f"Failed to get CDP targets: {e}")
            return []

    async def _resize_window(self, context: PlaywrightBrowserContext) -> None:
        """Resize the browser window to match the configured size"""
        try:
            if not context.pages:
                return

            page = context.pages[0]
            window_size = {
                "width": self.config.window_width,
                "height": self.config.window_height,
            }

            # First, set the viewport size
            await self.set_viewport_size(page)

            # Then, try to set the actual window size using CDP
            try:
                cdp_session = await context.new_cdp_session(page)

                # Get the window ID
                window_id_result = await cdp_session.send("Browser.getWindowForTarget")

                # Set the window bounds
                await cdp_session.send(
                    "Browser.setWindowBounds",
                    {
                        "windowId": window_id_result["windowId"],
                        "bounds": {
                            "width": window_size["width"],
                            "height": window_size["height"]
                            + BROWSER_NAVBAR_HEIGHT,  # Add height for browser chrome
                            "windowState": "normal",  # Ensure window is not minimized/maximized
                        },
                    },
                )

                await cdp_session.detach()
                logger.debug(
                    f'Set window size to {window_size["width"]}x{window_size["height"] + BROWSER_NAVBAR_HEIGHT}'
                )
            except Exception as e:
                logger.debug(f"CDP window resize failed: {e}")

                # Fallback to using JavaScript
                try:
                    await page.evaluate(
                        """
                        (width, height) => {
                            window.resizeTo(width, height);
                        }
                        """,
                        window_size["width"],
                        window_size["height"] + BROWSER_NAVBAR_HEIGHT,
                    )
                    logger.debug(
                        f'Used JavaScript to set window size to {window_size["width"]}x{window_size["height"] + BROWSER_NAVBAR_HEIGHT}'
                    )
                except Exception as e:
                    logger.debug(f"JavaScript window resize failed: {e}")

            logger.debug(
                f'Attempted to resize window to {window_size["width"]}x{window_size["height"]}'
            )
        except Exception as e:
            logger.debug(f"Failed to resize browser window: {e}")
            # Non-critical error, continue execution

    async def wait_for_element(self, selector: str, timeout: float) -> None:
        """
        Waits for an element matching the given CSS selector to become visible.

        Args:
                selector (str): The CSS selector of the element.
                timeout (float): The maximum time to wait for the element to be visible (in milliseconds).

        Raises:
                TimeoutError: If the element does not become visible within the specified timeout.
        """
        page = await self.get_agent_current_page()
        await page.wait_for_selector(selector, state="visible", timeout=timeout)
