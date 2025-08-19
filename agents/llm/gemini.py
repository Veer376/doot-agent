from dataclasses import dataclass
import os
import inspect
from functools import wraps
from google import genai
from google.genai import types
from typing import Callable, Sequence, Annotated, List, Dict, Any, Optional, Generator, TypedDict
from typing import get_origin, get_args
from langchain_core.messages import AIMessage
from langchain_core.messages.tool import ToolCall
import uuid
from google.genai import errors as genai_errors
from typing import Generic, TypeVar, Literal
from dotenv import load_dotenv
from .types import LLM, MessageBlueprintBase, LLMConfig, GeminiMessage
from logging_utils import get_llm_logger
from .usage_stats import get_usage_stats

load_dotenv()

logger = get_llm_logger("gemini")

    
class GeminiLLM(LLM):
    """Wrapper for Google's Gemini API to integrate with LangChain."""

    def __init__(self, model_name: str = None, provider: str = None):
        """Initialize the Gemini wrapper."""
        self.model_name = model_name or os.getenv("GEMINI_MODEL_NAME", "gemini-2.5-flash-lite")
        logger.info(f"Using model: {self.model_name}")
        api_key = os.getenv("GEMINI_API_KEY")
        
        if not api_key:
            raise ValueError("GEMINI_API_KEY environment variable not set.")
        
        self.client = genai.Client(api_key=api_key)

    async def __call__(
        self, message_plan: MessageBlueprintBase, tools: list[Callable]|None = None, config: LLMConfig | None = None
    ) -> GeminiMessage:
        """Get response from Gemini API and convert it to GeminiMessage format."""

        from langchain_core.tools import InjectedToolArg
        processed_tools = []
        for tool in tools if tools else []:
            try:
                processed_tool = self.strip_injected_args(tool, InjectedToolArg)
                processed_tools.append(processed_tool)
                
            except Exception as e:
                logger.critical(f"Warning: Failed to strip injected args from tool {tool.__name__}: {e}")
                processed_tools.append(tool)


        system_instructions, contents = message_plan.to_gemini_format()
        
        async def get_response():
            return await self.client.aio.models.generate_content(
                model=self.model_name,
                contents=contents,
                config=types.GenerateContentConfig(
                    system_instruction=system_instructions,
                    tools=processed_tools,
                    temperature=config.temperature,
                    automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
                    thinking_config=types.ThinkingConfig(
                        include_thoughts=True,
                        thinking_budget=(
                            config.thinking_budget if config and hasattr(config, "thinking_budget") else 0
                        ),
                    ),
                )
            )
        try:
            response = await get_response()
        except genai_errors.ServerError as e:
            if e.status == 500:
                logger.warning(f"🌩️ Gemini struck by a 500 thunderbolt — staging comeback in 2s")
                import asyncio
                await asyncio.sleep(2)
                try:
                    response = await get_response()
                except Exception as e:
                    logger.error(f"Retry failed: {e}", exc_info=True)
                    raise e
            else:
                logger.error(f"Gemini API returned a {e.status} error")
                raise e
        except Exception as e:
            logger.error(f"Gemini API call failed: {e}", exc_info=True)
            raise e
        
        # Track usage statistics
        usage_stats = get_usage_stats()
        if response and response.usage_metadata:
            usage_stats.update_from_gemini(self.model_name, response.usage_metadata)
            
        text: str = ""
        tool_calls: list[ToolCall] = []
        thought: str = ""
        parts: list[types.Part] = []
                
        if response and response.candidates:
            content = response.candidates[0].content
            for part in getattr(content, "parts", []):
                part: types.Part
                parts.append(part)
                
                if getattr(part, "thought", False) and hasattr(part, "text") and part.text:
                    thought = part.text
        
                elif hasattr(part, "function_call") and part.function_call:
                    id = part.function_call.id or str(uuid.uuid4())
                    
                    # Assigning the ID to the function_call as well.
                    part.function_call.id = id

                    tool_call = ToolCall(
                        name=part.function_call.name,
                        args=part.function_call.args,
                        id=part.function_call.id,
                    )
                    tool_calls.append(tool_call)
        
                elif hasattr(part, "text") and part.text:
                    text = part.text
                                    
                
        message = GeminiMessage(
            content=text,
            tool_calls=tool_calls,
            thought=thought,
            parts=[part.to_json_dict() for part in parts if hasattr(part, "to_json_dict")] # Convert parts to JSON dict for serializability.
        )

        return message
    
    
    def strip_injected_args(self, func, injected_type):
        """
        Removes parameters that are annotated with the specified injected_type.

        Args:
            func: The function to strip injected arguments from
            injected_type: The type of annotation to look for and remove

        Returns:
            A wrapped function with the same functionality but without the injected parameters
            in its signature.
        """
        sig = inspect.signature(func)
        new_params = []

        for param in sig.parameters.values():
            annotation = param.annotation

            # Check if the param is Annotated[..., InjectedToolArg]
            if get_origin(annotation) is Annotated:
                args = get_args(annotation)
                if injected_type in args:
                    continue  # Skip this param

            new_params.append(param)

        # Handle both coroutine and regular functions properly
        if inspect.iscoroutinefunction(func):
            @wraps(func)
            async def wrapper(*args, **kwargs):
                return await func(*args, **kwargs)
        else:
            @wraps(func)
            def wrapper(*args, **kwargs):
                return func(*args, **kwargs)

        wrapper.__signature__ = inspect.Signature(parameters=new_params, return_annotation=sig.return_annotation)
        wrapper.__doc__ = func.__doc__
        # Make sure the wrapper function has the same name property as the original
        wrapper.__name__ = func.__name__
        return wrapper
