# filepath: c:\Users\aryav\projects\orbitagent\browser_use_agent\services\browser.py
from playwright.async_api import async_playwright, Page, Browser, Playwright
from google.genai import types
import io
from typing import Optional, Any
from pydantic import BaseModel, Field
from datetime import datetime
from .schema import BrowserActionResult
from ..utils.logger import browser_info, browser_error
class Browser:
    def __init__(self, use_debug_chrome: bool = False):
        self.viewport_width = 1280
        self.viewport_height = 800
        self.auto_switch_to_new_tabs = True 
        self.all_pages = [] 
        self.use_debug_chrome = use_debug_chrome
        self.chrome_path = "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe" if use_debug_chrome else None
        self.debug_port = 9222 
        self.user_data_dir = "./chrome-user-data" if use_debug_chrome else None
        
        self.headless = False
    
    async def initialize(self):
        try:
            self.playwright = await async_playwright().start()
            
            # Common browser arguments for both modes
            browser_args = [
                "--disable-extensions", 
                "--disable-file-system", 
                "--start-maximized",
            ]
            
            # Add debug port if specified
            if self.debug_port:
                browser_args.append(f"--remote-debugging-port={self.debug_port}")
            
            # Common launch options for both modes
            common_options = {
                "headless": self.headless,
            }
            
            # Use custom Chrome path if specified
            if self.chrome_path:
                common_options["executable_path"] = self.chrome_path
                
            common_options["args"] = browser_args
            
            # Initialize browser based on chosen mode
            if self.use_debug_chrome:
                self.context = await self.playwright.chromium.launch_persistent_context(
                    user_data_dir=self.user_data_dir,
                    **common_options
                )
                
                self.browser = self.context
            else:
                # Launch standard sandboxed browser
                browser_info(f"Launching sandboxed browser")
                # In sandbox mode, we have a browser object that creates contexts
                self.browser = await self.playwright.chromium.launch(**common_options)
                self.context = await self.browser.new_context(no_viewport=True)  # No initial viewport in sandbox mode
            
            self.page = await self.context.new_page()
            
            # Initialize page tracking
            self.all_pages = list(self.context.pages)
            browser_info(f"Browser initialized with viewport")
            return True
        except Exception as e:
            browser_error(f"Error initializing browser: {e}")
            
            # Close context if it exists
            if hasattr(self, 'context') and self.context:
                await self.context.close()
                
            # Close browser if it's different from context
            if hasattr(self, 'browser') and self.browser and hasattr(self, 'context') and self.browser != self.context:
                await self.browser.close()
                
            # Always stop playwright
            if hasattr(self, 'playwright') and self.playwright:
                await self.playwright.stop()
                
            return False
                
    async def navigate(self, url: str) -> BrowserActionResult:
        try:
            # Store page count before navigation
            initial_pages = len(self.context.pages)
            
            await self.page.goto(url, wait_until='load', timeout=60000) # Wait for load, reasonable timeout
            
            # Check if navigation created new tabs (redirects, popups, etc.)
            if len(self.context.pages) > initial_pages:
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
            # Close context first
            if hasattr(self, 'context') and self.context:
                await self.context.close()
                
            # Only close browser separately if it's different from context
            # (In persistent mode, browser == context)
            if hasattr(self, 'browser') and self.browser and self.browser != self.context:
                await self.browser.close()
                
            # Always stop playwright
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
            
    async def click_coordinates(self, x: float = 0, y: float = 0, label: str = None, button: str = "left", timeout: int = 5000, delay_after: int = 500) -> BrowserActionResult:
        
        try:
            # Store page count before click
            initial_pages = len(self.context.pages)
            
            new_tab_opened = False
            
            await self.page.mouse.click(x, y)

            if len(self.context.pages) > initial_pages:
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
            focused = await self.page.evaluate("""
                () => {
                  const el = document.activeElement;
                  return {
                    tag: el?.tagName,
                    isContentEditable: el?.isContentEditable
                  }
                }
                """)
            
            if not (focused["tag"].upper() in ["INPUT", "TEXTAREA"] or focused["isContentEditable"]):
                raise ValueError("No focusable input field selected.")

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
                pointer.id = 'ai-pointer';                
                pointer.style.cssText = `
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

        current_pages = self.context.pages
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
        for i, page in enumerate(self.context.pages):
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
    
    async def show_pointer_pro(self, x:float, y:float):
        try: 
            js_code = r"""(coords) => {
    // Remove existing cursor animations
    document.querySelectorAll('.ai-cursor-container, .ai-cursor-splash').forEach(el => el.remove());

    const container = document.createElement('div');
    container.className = 'ai-cursor-container';
    container.style.cssText = `
        position: fixed;
        left: ${coords.x}px;
        top: ${coords.y}px;
        pointer-events: none;
        z-index: 2147483647;
    `;
    document.body.appendChild(container);

    const cursor = document.createElement('div');
    cursor.className = 'ai-cursor-icon';
    cursor.innerHTML = `
        <svg width="24" height="24" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
            <path d="M3 3L10.07 19.97L12.58 12.58L19.97 10.07L3 3Z" fill="#3b82f6" stroke="#1e40af" stroke-width="1"/>
        </svg>
    `;
    cursor.style.cssText = `
        position: absolute;
        transform: translate(-12px, -12px);
        transition: all 0.3s ease-in-out;
        filter: drop-shadow(0 4px 6px rgba(0, 0, 0, 0.1));
    `;
    container.appendChild(cursor);

    setTimeout(() => {
        cursor.style.opacity = '0';
        cursor.style.transform = 'translate(-12px, -12px) scale(0.8)';
        cursor.animate([
            { opacity: 0, transform: 'translate(-12px, -12px) scale(0.8)' },
            { opacity: 1, transform: 'translate(-12px, -12px) scale(1)' }
        ], {
            duration: 300,
            fill: 'forwards'
        });

        setTimeout(() => {
            cursor.animate([
                { transform: 'translate(-12px, -12px) scale(1) rotate(0deg)' },
                { transform: 'translate(-12px, -12px) scale(0.9) rotate(15deg)' },
                { transform: 'translate(-12px, -12px) scale(1) rotate(0deg)' }
            ], {
                duration: 300,
                easing: 'ease-in-out'
            });

            const ripple = document.createElement('div');
            ripple.className = 'ai-cursor-ripple';
            ripple.style.cssText = `
                position: absolute;
                width: 40px;
                height: 40px;
                border: 2px solid #3b82f6;
                border-radius: 50%;
                transform: translate(-20px, -20px);
                opacity: 0.7;
            `;
            container.appendChild(ripple);

            ripple.animate([
                { transform: 'translate(-20px, -20px) scale(0.5)', opacity: 0.7 },
                { transform: 'translate(-20px, -20px) scale(2)', opacity: 0 }
            ], {
                duration: 600,
                easing: 'ease-out'
            });

            setTimeout(() => {
                createSplashEffect(container);
            }, 200);

        }, 1000);

    }, 100);

    function createSplashEffect(container) {
        const splashContainer = document.createElement('div');
        splashContainer.className = 'ai-cursor-splash';
        splashContainer.style.cssText = `
            position: absolute;
            transform: translate(-50px, -50px);
        `;
        container.appendChild(splashContainer);

        for (let i = 0; i < 3; i++) {
            const circle = document.createElement('div');
            circle.style.cssText = `
                position: absolute;
                width: ${80 + i * 20}px;
                height: ${80 + i * 20}px;
                border-radius: 50%;
                background: linear-gradient(45deg, #3b82f6, #8b5cf6);
                opacity: ${0.3 - i * 0.1};
                transform: translate(-50%, -50%);
            `;
            splashContainer.appendChild(circle);

            circle.animate([
                { transform: 'translate(-50%, -50%) scale(0.5)', opacity: 0.3 - i * 0.1 },
                { transform: 'translate(-50%, -50%) scale(3)', opacity: 0 }
            ], {
                duration: 600,
                delay: i * 75,
                easing: 'ease-out'
            });
        }

        const numberOfParticles = 8;
        for (let i = 0; i < numberOfParticles; i++) {
            const particle = document.createElement('div');
            const angle = (i / numberOfParticles) * 360;
            const distance = 30 + Math.random() * 20;
            const radians = angle * Math.PI / 180;
            const endX = Math.cos(radians) * distance;
            const endY = Math.sin(radians) * distance;

            particle.style.cssText = `
                position: absolute;
                width: 8px;
                height: 8px;
                background: linear-gradient(45deg, #3b82f6, #8b5cf6);
                border-radius: 50%;
                transform: translate(-4px, -4px);
            `;
            splashContainer.appendChild(particle);

            particle.animate([
                { transform: 'translate(-4px, -4px) scale(1)', opacity: 0.8 },
                { transform: 'translate(${endX}px, ${endY}px) scale(0)', opacity: 0 }
            ], {
                duration: 800,
                delay: i * 50,
                easing: 'ease-out'
            });
        }
    }

    setTimeout(() => {
        container.remove();
    }, 2500);
}"""

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