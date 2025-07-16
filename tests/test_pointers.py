import asyncio
import os
from src.browser.browser import Browser

async def test_pointers():
    """Test both pointer functions with our test HTML page."""
    # Initialize the browser
    browser = Browser()
    
    try:
        # Initialize the browser
        initialized = await browser.initialize()
        if not initialized:
            print("Failed to initialize browser")
            return

        # Get the absolute path to the test HTML file
        current_dir = os.path.dirname(os.path.abspath(__file__))
        html_path = os.path.join(current_dir, "test_pointer.html")
        file_url = f"file://{html_path}"
        
        # Navigate to the test page
        result = await browser.navigate(file_url)
        print(f"Navigation result: {result.message}")
        
        # Wait for the page to be fully loaded
        await asyncio.sleep(2)
            
        print("\n===== Testing Advanced Pointer (show_pointer_pro) =====")
        # Test the pro pointer on Box 2
        x, y = 600, 200  # Coordinates for the center of Box 2
        print(f"Showing advanced pointer at coordinates: ({x}, {y})")
        result = await browser.show_pointer_pro(x, y)
        print(f"Result: {result.message}")
        
        await asyncio.sleep(10)
        
    except Exception as e:
        print(f"Error during test: {e}")
    finally:
        # Close the browser
        await browser.close()
        print("Browser closed")

if __name__ == "__main__":
    asyncio.run(test_pointers())
    
    