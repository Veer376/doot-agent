import asyncio
import os
import sys

# Add the parent directory of `browser_use` to the Python path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

from agents.browser_agent.toolkit.tools import click_element
from browser_use.browser import Browser, BrowserConfig
from agents.browser_agent.toolkit.tools import scroll, find, extract, type_text


async def test_dropdown():
    browser = Browser(
        config=BrowserConfig(
            headless=False,
            browser_binary_path="C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe",
        )
    )

    async with await browser.new_context() as browser_context:

        page = await browser_context.get_current_page()
        await page.goto(
            "https://docs.google.com/forms/d/e/1FAIpQLSfEYOarcFQAl3uWPwJhkj85cT9-05zh3W3zdYCbpGsOf-Vw5Q/viewform"
        )

        total_tests = 0
        passed_tests = 0
        options = ["Me", "Galgotia", "Nothing", "Option"]

        for i in range(1, 40):
            try:
                page = await browser_context.get_current_page()
                await page.reload()
                await asyncio.sleep(0.5)

                await browser_context.get_state(cache_clickable_elements_hashes=True)
                await asyncio.sleep(0.5)

                element_node = await browser_context.get_dom_element_by_index(1)
                if not element_node:
                    continue

                total_tests += 1
                index = i % len(options)
                option = options[index]
                element_handle = await browser_context.get_locate_element(element_node)
                await element_handle.wait_for_element_state("stable")
                await element_handle.click()
                await asyncio.sleep(1)
                await page.keyboard.type(option, delay=100)
                await page.keyboard.press("Enter", delay=50)
                
                await asyncio.sleep(2)
                details = await browser_context.get_dropdown_details(element_node)
                
                selected_options = details.get("selected_options", [])
                
                if not selected_options:
                    print(f"Test {i}: Failed - Expected option: {option}, got no selection")
                    continue
                
                selected_option = selected_options[0] if selected_options else {}
                
                if option == selected_option.get("value", "") or option == selected_option.get("text", ""):
                    print(f"Test {i}: Passed - Selected option matched '{option}'")
                    passed_tests += 1

                else:
                    print(f"Test {i}: Failed - Expected option: {option}, got {selected_option.get('value', '')}")
                    
            except Exception as e:
                print(f"Test {i}: Error - {str(e)}")

        print(
            f"Total tests: {total_tests}, Passed: {passed_tests}, Failed: {total_tests - passed_tests}"
        )


asyncio.run(test_dropdown())
