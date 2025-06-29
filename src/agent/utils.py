import os
from dotenv import load_dotenv
from langchain.chat_models import init_chat_model

def get_model():
    """Initialize and return the chat model based on environment variables."""
    load_dotenv()
    try:
        model_provider = os.getenv("MODEL_PROVIDER")
        model_name = os.getenv("MODEL_NAME")
        
        if model_provider and model_name:
            return init_chat_model(f"{model_provider}:{model_name}")
        else:
            return init_chat_model("google_genai:gemini-2.0-flash")
        
    except Exception as e:
        print(f"Error initializing model: {e}")
        import traceback
        traceback.print_exc()
        raise
    
    
SYSTEM_MESSAGE = """
You are a browser automation agent. 
Your task is to perform actions in a web browser to complete a user's goal.
You will be provided with the current screenshot of the browser, the user's goal.
Based on the user's goal, and the current state of the browser, you will decide which action to take next.

ACTIONS:
1. click_element: Use this tool to click on the elements like links, buttons, dropdown etc. You will pass the label/element to be clicked on with the screenshot url.
2. type_text: Use this tool to type text in an input field. Takes text and label as arguments.
3. press_keys: Use this tool to press keys on the keyboard like 'Enter', 'Backspace', etc. You will pass the keys to be pressed as a list.
4. go_back: Use this tool to go back to the previous page in the browser history.
5. wait: Use this tool to wait for a specified amount of time. 

INSTRUCTIONS:
- Only wait using wait_tool if page is still loading, waiting to verify captcha, or if user requested.
- To search must press the Enter key after typing in the search box.
"""


def correct_coordinates(x, y, viewport_width=1280, viewport_height=800):
    
    model_coord_range = 1000.0

    x_scale_factor = viewport_width / model_coord_range
    y_scale_factor = viewport_height / model_coord_range

    x_original = x * x_scale_factor
    y_original = y * y_scale_factor

    return x_original, y_original
