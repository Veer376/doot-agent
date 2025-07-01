# filepath: c:\Users\aryav\projects\orbitagent\browser_use_agent\services\browser.py
from playwright.async_api import async_playwright, Page, Browser, Playwright
from google.genai import types
import io
from typing import Optional, Any
from pydantic import BaseModel, Field
from datetime import datetime
from .schema import BrowserActionResult

class Browser:
    def __init__(self, viewport_width=1280, viewport_height=800):
        self.viewport_width = viewport_width
        self.viewport_height = viewport_height
        self.auto_switch_to_new_tabs = True  # Automatically switch to new tabs when they're created
        self.all_pages = []  # Track all pages for tab management
    
    async def initialize(self):
        try:
            self.playwright = await async_playwright().start()
            self.browser = await self.playwright.chromium.launch(
                headless=False, # Keep False for debugging, True for headless
                chromium_sandbox=True,
                env={},
                args=["--disable-extensions", "--disable-file-system"]
            )
            self.page = await self.browser.new_page()
            await self.page.set_viewport_size({"width": self.viewport_width, "height": self.viewport_height})
            print(f"[BROWSER] Browser initialized with viewport: {self.viewport_width}x{self.viewport_height}")
            # Initialize tab tracking
            self.all_pages = [self.page]
            return True
        except Exception as e:
            print(f"[BROWSER] Error initializing browser: {e}")
            if hasattr(self, 'browser') and self.browser:
                await self.browser.close()
            if hasattr(self, 'playwright') and self.playwright:
                await self.playwright.stop()
            return False
                
    async def navigate(self, url: str) -> BrowserActionResult:
        try:
            # Store page count before navigation (browser-use approach)
            initial_pages = len(self.browser.contexts[0].pages)
            
            await self.page.goto(url, wait_until='load', timeout=60000) # Wait for load, reasonable timeout
            
            # # # Check if navigation created new tabs (redirects, popups, etc.)
            if len(self.browser.contexts[0].pages) > initial_pages:
                await self._switch_to_newest_tab()
                
            return BrowserActionResult.create_success(
                action_type="navigate",
                message=f"Navigated to {url}",
            )
        except Exception as e:
            return BrowserActionResult.create_failure(
                action_type="navigate",
                message=f"Error navigating to {url}: {str(e)}",
            )
            
    async def close(self) -> BrowserActionResult:
        try:
            if hasattr(self, 'browser') and self.browser:
                await self.browser.close()
            if hasattr(self, 'playwright') and self.playwright:
                await self.playwright.stop()
            return BrowserActionResult.create_success(
                action_type="close",
                message="Browser successfully closed",
            )
        except Exception as e:
            return BrowserActionResult.create_failure(
                action_type="close",
                message=f"Error closing browser: {str(e)}",
            )
        
    async def screenshot_bytes(self, iteration=None) -> types.Part:
        try:
            screenshot_bytes = await self.page.screenshot()
            return screenshot_bytes
        except Exception as e:
            return str(e)

    async def screenshot_part(self) -> BrowserActionResult:
        try:
            # Take the screenshot
            screenshot_bytes = await self.page.screenshot()
            
            # Convert to Part object for the model
            # image_stream = io.BytesIO(screenshot_bytes)
            # img = Image.open(image_stream)
            # img = img.convert('L') # Keep color for better model interpretation
            
            # Optional resizing (consider if needed for performance vs. model accuracy)
            # scale_factor = min(640 / width, 640 / height)
            # new_width = int(width * scale_factor)
            # new_height = int(height * scale_factor)
            # img = img.resize((new_width, new_height))
            
            # output_stream = io.BytesIO()
            # # Use PNG for lossless quality, JPEG if size is critical
            # img.save(output_stream, format="PNG")
            # output_bytes = output_stream.getvalue()
            
            part_data = types.Part(
                inline_data=types.Blob(
                    mime_type="image/png",
                    data=screenshot_bytes,
                )
            )
            return BrowserActionResult.create_success(
                action_type="screenshot",
                message="Screenshot part captured successfully",
                data={"part": part_data}
            )
        except Exception as e:
            return BrowserActionResult.create_failure(
                action_type="screenshot",
                message=f"Error taking screenshot part: {str(e)}",
            )
            
    async def click(self, x: float = 0, y: float = 0, label: str = None, button: str = "left", timeout: int = 5000, delay_after: int = 500) -> BrowserActionResult:
        
        try:
            # Store page count before click (browser-use approach)
            initial_pages = len(self.browser.contexts[0].pages)
            
            # await self.page.mouse.click(x, y, button=button)
            elements = await self.page.locator("text=BookMyShow").all()

            for e in elements:
                tag = await e.evaluate("el => el.tagName")
                href = await e.get_attribute("href")
                if tag == "A" and href:
                    await e.click()
                    break

            new_tab_opened = False
            if len(self.browser.contexts[0].pages) > initial_pages:
                new_tab_opened = await self._switch_to_newest_tab()
            
            success_message = f"Successfully clicked at coordinates ({x},{y}), label: '{label}'"
            if new_tab_opened:
                success_message += " - New tab opened, switched to it"
                
            return BrowserActionResult.create_success(
                action_type="click",
                message=success_message,
            )
        except Exception as e:
            return BrowserActionResult.create_failure(
                action_type="click",
                message=f"Error clicking at coordinates ({x},{y}): {str(e)}",
            )
            
    async def scroll(self, direction: str = "down", amount: int = 500, x: float = None, y: float = None, delay_after: int = 500) -> BrowserActionResult:
        
        try:
            await self.page.mouse.move(x, y)
            
            scroll_delta_y = amount if direction == "down" else -amount
            
            await self.page.mouse.wheel(0, scroll_delta_y)
            await self.page.wait_for_timeout(delay_after)
            return BrowserActionResult.create_success(
                action_type="scroll",
                message=f"Successfully scrolled {direction} by {amount} pixels",
            )
        except Exception as e:
            return BrowserActionResult.create_failure(
                action_type="scroll",
                message=f"Error scrolling {direction}: {str(e)}",
            )
            
    async def type(self, text: str, label: str = None, delay: int = 50, timeout: int = 10000, delay_after: int = 200) -> BrowserActionResult:
        label = label or '[NO LABEL]'
        try:
            await self.page.keyboard.type(text, delay=delay)
            await self.page.wait_for_timeout(delay_after)
            return BrowserActionResult.create_success(
                action_type="type",
                message=f"Typed text: '{text}' into field: '{label}'",
            )
        except Exception as e:
            return BrowserActionResult.create_failure(
                action_type="type",
                message=f"Error typing text '{text}': {str(e)}",
            )
            
    async def press_keys(self, keys, delay_after: int = 200) -> BrowserActionResult:
        try:
            pressed_keys = []
            for key in keys:
                pw_key = key
                if key.lower() == "enter":
                    pw_key = "Enter"
                elif key.lower() == "tab":
                    pw_key = "Tab"
                elif key.lower() == "escape" or key.lower() == "esc":
                    pw_key = "Escape"
                
                await self.page.keyboard.press(pw_key)
                pressed_keys.append(pw_key)
                
                if pw_key == "Enter":
                    try:
                        await self.page.wait_for_load_state("load", timeout=10000)
                    except Exception as e:
                        try:
                            await self.page.wait_for_load_state("networkidle", timeout=5000)
                        except Exception as ne:
                            await self.page.wait_for_timeout(2000)
                else:
                    await self.page.wait_for_timeout(delay_after)
            return BrowserActionResult.create_success(
                action_type="press_keys",
                message=f"Successfully pressed keys: {', '.join(pressed_keys)}",
            )
        except Exception as e:
            return BrowserActionResult.create_failure(
                action_type="press_keys",
                message=f"Error pressing keys: {str(e)}",
            )
            
    async def go_back(self, delay_after: int = 1000) -> BrowserActionResult:
        try:
            await self.page.go_back()
            await self.page.wait_for_timeout(delay_after)
            return BrowserActionResult.create_success(
                action_type="go_back",
                message="🔙  Navigated back",
            )
        except Exception as e:
            return BrowserActionResult.create_failure(
                action_type="go_back",
                message=f"Error navigating back: {str(e)}",
            )
    
    async def show_pointer(self, x: float, y: float):
        try:

            await self.page.wait_for_load_state("domcontentloaded")
            
            js_code = """(coords) => {                // Remove existing pointer if any
                const existingPointer = document.getElementById('ai-pointer');
                if (existingPointer) existingPointer.remove();
                
                // Create pointer element
                const pointer = document.createElement('div');
                pointer.id = 'ai-pointer';                pointer.style.cssText = `
                    position: fixed;
                    width: 8px;
                    height: 8px;
                    background: rgba(255, 0, 0, 0.7);
                    border: 3px solid white;
                    border-radius: 50%;
                    pointer-events: none;
                    transform: translate(-50%, -50%);
                    z-index: 2147483647;
                    left: ${coords.x}px;
                    top: ${coords.y}px;
                    box-shadow: 0 0 15px red;
                `;
                
                // Add CSS animation
                const style = document.createElement('style');
                style.textContent = `
                    @keyframes pulse {
                        0% { transform: translate(-50%, -50%) scale(1); opacity: 1; }
                        50% { transform: translate(-50%, -50%) scale(1.5); opacity: 0.7; }
                        100% { transform: translate(-50%, -50%) scale(1); opacity: 1; }
                    }
                    #ai-pointer {
                        animation: pulse 1s infinite;
                    }
                `;
                document.head.appendChild(style);
                
                // Append pointer to body
                document.body.appendChild(pointer);
                
                // Create ripple effect
                setInterval(() => {
                    const ripple = pointer.cloneNode();
                    ripple.style.animation = 'none';
                    document.body.appendChild(ripple);
                    ripple.animate([
                        { transform: 'translate(-50%, -50%) scale(1)', opacity: 0.5 },
                        { transform: 'translate(-50%, -50%) scale(2)', opacity: 0 }
                    ], {
                        duration: 1000,
                        easing: 'ease-out'
                    }).onfinish = () => ripple.remove();
                }, 2000);
                  // Verify pointer creation
                return !!document.getElementById('ai-pointer');}"""
            
            print(f"[BROWSER] Attempting to show pointer at coordinates: ({x}, {y})")
            # Pass coordinates as a dictionary to match the JavaScript parameters
            result = await self.page.evaluate(js_code, {'x': x, 'y': y})
            
            if result:
                print(f"[BROWSER] Pointer created successfully at ({x}, {y})")
                return BrowserActionResult.create_success(
                    action_type="show_pointer",
                    message=f"Successfully showed pointer at coordinates ({x},{y})",
                )
            else:
                raise Exception("Failed to create pointer element")
        except Exception as e:
            print(f"[BROWSER] Error showing pointer: {e}")
            return BrowserActionResult.create_failure(
                action_type="show_pointer",
                message=f"Error showing pointer: {str(e)}",
            )
        
    async def hide_pointer(self):
        """Remove the visual pointer."""
        try:
            js_code = """() => {
                const pointer = document.getElementById('ai-pointer');
                if (pointer) pointer.remove();
            }"""
            await self.page.evaluate(js_code)
            return BrowserActionResult.create_success(
                action_type="hide_pointer",
                message="Successfully removed pointer",
            )
        except Exception as e:
            print(f"[BROWSER] Error removing pointer: {e}")
            return BrowserActionResult.create_failure(
                action_type="hide_pointer",
                message=f"Error removing pointer: {str(e)}",
            )
    
    async def _switch_to_newest_tab(self):

        if not self.auto_switch_to_new_tabs:
            return False

        current_pages = self.browser.contexts[0].pages
        # Trust the caller - they already detected new tabs
        newest_page = current_pages[-1]  # Get the most recent page
        
        # Update our tracking
        self.page = newest_page
        self.all_pages = list(current_pages)
        
        # Bring to front and ensure it's ready
        await self.page.bring_to_front()
        await self.page.wait_for_load_state("domcontentloaded", timeout=5000)
        
        # Set viewport size for the new tab
        await self.page.set_viewport_size({"width": self.viewport_width, "height": self.viewport_height})

        print(f"[BROWSER] 🔄 Switched to new tab: {self.page.url}")
        return True
    
    def set_auto_switch_tabs(self, enabled: bool):
        """Enable or disable automatic switching to new tabs"""
        self.auto_switch_to_new_tabs = enabled
        print(f"[BROWSER] Auto-switch to new tabs: {'enabled' if enabled else 'disabled'}")
        
    async def get_all_tabs_info(self):
        """Get information about all open tabs"""
        tabs_info = []
        for i, page in enumerate(self.browser.pages):
            try:
                title = await page.title()
                tabs_info.append({
                    "index": i,
                    "url": page.url,
                    "title": title,
                    "is_current": page == self.page
                })
            except Exception as e:
                tabs_info.append({
                    "index": i,
                    "url": page.url,
                    "title": f"Error getting title: {str(e)}",
                    "is_current": page == self.page
                })
        return tabs_info
    
    async def show_pointer_pro(self, x: float, y: float):
        """Add an advanced visual pointer with click and splash animation."""
        try:
            await self.page.wait_for_load_state("domcontentloaded")

            js_code = """(coords) => {
                // Remove existing custom pointers and splash elements
                document.querySelectorAll('.ai-pointer-pro-container, .ai-splash-line').forEach(el => el.remove());

                const container = document.createElement('div');
                container.className = 'ai-pointer-pro-container';
                container.style.cssText = `
                    position: fixed;
                    left: ${coords.x}px;
                    top: ${coords.y}px;
                    transform: translate(-50%, -50%);
                    pointer-events: none;
                    z-index: 2147483647;
                `;
                document.body.appendChild(container);

                // Create and animate splash lines
                const numberOfLines = 12; // Increased number of lines for a fuller splash
                const lineLength = 30; // Increased line length
                const animationDuration = 1000; // milliseconds
                const initialOffset = 5; // distance from center before animation
                const finalOffset = lineLength * 2; // distance from center after animation

                for (let i = 0; i < numberOfLines; i++) {
                    const line = document.createElement('div');
                    line.className = 'ai-splash-line';
                    const angle = (i / numberOfLines) * 360;
                    const radians = angle * Math.PI / 180;

                    line.style.cssText = `
                        position: absolute;
                        width: 2px;
                        height: ${lineLength}px;
                        background: rgba(255, 255, 255, 0.8); /* White lines with some transparency */
                        opacity: 1;
                        transform-origin: 50% 50%;
                        /* Position at center, rotate, and translate outwards */
                        transform: translate(-1px, -${lineLength / 2}px) rotate(${angle}deg) translate(0px, ${initialOffset}px);
                    `;

                    container.appendChild(line);

                    // Animate lines outwards and fade out
                    line.animate([
                        { transform: `translate(-1px, -${lineLength / 2}px) rotate(${angle}deg) translate(0px, ${initialOffset}px)`, opacity: 1 },
                        { transform: `translate(-1px, -${lineLength / 2}px) rotate(${angle}deg) translate(0px, ${finalOffset}px)`, opacity: 0 }
                    ], {
                        duration: animationDuration,
                        easing: 'ease-out',
                        fill: 'forwards'
                    });
                }

                // Optional: Add a central pulsing dot before the splash (simulating the click point)
                const clickDot = document.createElement('div');
                clickDot.className = 'ai-click-dot';
                clickDot.style.cssText = `
                    position: absolute;
                    width: 10px;
                    height: 10px;
                    background: red;
                    border-radius: 50%;
                    top: 50%;
                    left: 50%;
                    transform: translate(-50%, -50%);
                    opacity: 1;
                `;
                container.appendChild(clickDot);

                 clickDot.animate([
                    { transform: 'translate(-50%, -50%) scale(1)', opacity: 1 },
                    { transform: 'translate(-50%, -50%) scale(1.5)', opacity: 0.5 },
                    { transform: 'translate(-50%, -50%) scale(1)', opacity: 1 }
                ], {
                    duration: 500, // Quick pulse
                    iterations: 1
                });


                // Remove container after animation
                setTimeout(() => {
                    container.remove();
                }, animationDuration + 100); // Add a small delay after line animation

                return true; // Indicate success
            }"""

            print(f"[BROWSER] Attempting to show advanced pointer at coordinates: ({x}, {y})")
            # Pass coordinates as a dictionary to match the JavaScript parameters
            result = await self.page.evaluate(js_code, {'x': x, 'y': y})

            if result:
                print(f"[BROWSER] Advanced pointer created successfully at ({x}, {y})")
                return BrowserActionResult.create_success(
                    action_type="show_pointer_pro",
                    message=f"Successfully showed advanced pointer at coordinates ({x},{y})",
                )
            else:
                raise Exception("Failed to create advanced pointer elements")
        except Exception as e:
            print(f"[BROWSER] Error showing advanced pointer: {e}")
            return BrowserActionResult.create_failure(
                action_type="show_pointer_pro",
                message=f"Error showing advanced pointer: {str(e)}",
            )
