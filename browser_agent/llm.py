"""
Integration with Google's Generative AI (Gemini) for browser agent interactions.
This module provides a drop-in replacement for the default LLM in the browser agent.

Uses the new google-genai SDK (https://ai.google.dev/gemini-api/docs).
"""

from langchain.chat_models import init_chat_model
import os
import asyncio
from typing import Any, Dict, List, Optional, Sequence, Union
from google import genai
from google.genai import types
from dotenv import load_dotenv
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage, ToolMessage
import logging

logger = logging.getLogger(__name__)


class GeminiChatMessage:
    """Wrapper for Gemini API messages for better compatibility with langgraph."""
    
    def __init__(self, response, usage_metadata=None):
        self.response = response
        self.content = response.text
        self.tool_calls = []  # Initialize empty, will populate if there are function calls
        self.usage_metadata = usage_metadata or {}
        
        # Process any function calls in the response
        if hasattr(response, 'candidates') and response.candidates:
            for candidate in response.candidates:
                if hasattr(candidate, 'content') and candidate.content:
                    for part in candidate.content.parts:
                        if hasattr(part, 'function_call'):
                            # Extract function call details from the new SDK format
                            self.tool_calls.append({
                                "id": part.function_call.id or f"call_{len(self.tool_calls)}",
                                "name": part.function_call.name,
                                "args": part.function_call.args
                            })

    def __str__(self):
        return self.content

class InitChatModel:
    def __init__(self, model_provider: str | None = None, model_name: str | None = None):
        if not model_provider or not model_name:
            self.model_provider = os.getenv("MODEL_PROVIDER", "google_genai")
            self.model_name = os.getenv("MODEL_NAME", "gemini-2.0-flash")
            
    def get_model(self):
        return init_chat_model(f"{self.model_provider}:{self.model_name}")
    
class GoogleGenAiWrapperLLM:
    """Wrapper class for google-genai-sdk to integrate with LangGraph."""

    def __init__(self, model: str, temperature: float|None = None, top_p: float|None = None, thinking: types.ThinkingConfig|None = None, grounding: bool = False):
        self.config = {
            "model": model,
            "temperature": temperature,
            "top_p": top_p,
            "thinking": thinking,
            "grounding": grounding
        }

    def bind_tools(self, tools):
        self.tools = tools
        return self
    
    async def ainvoke(self, messages: Sequence[BaseMessage]) -> AIMessage:
        """Async invoke method for compatibility with LangChain."""
        
        # Convert messages to Gemini format
        contents = [self._convert_to_genai_format(msg) for msg in messages]
        
        # Set up function calling if tools are provided
        if self.tools:
            # Update the config with tools - using pure Python functions directly
            config = types.GenerateContentConfig(
                temperature=self.config.temperature,
                top_p=self.config.top_p,
                max_output_tokens=self.config.max_output_tokens,
                tools=self.tools,  # Pure Python functions passed directly
            )
        else:
            config = self.config
        
        try:
            # Call the Gemini API using the client
            response = await self.client.aio.models.generate_content(
                model=self.model_name,
                contents=contents,
                config=config,
            )
            
            # Calculate usage for token tracking
            usage_metadata = {
                "prompt": getattr(response, "prompt_token_count", 0),
                "completion": (
                    response.candidates[0].token_count 
                    if hasattr(response, "candidates") and response.candidates 
                    else 0
                ),
                "total": (
                    getattr(response, "prompt_token_count", 0) + 
                    (response.candidates[0].token_count if hasattr(response, "candidates") and response.candidates else 0)
                ),
            }
            
            # Create message wrapper for compatibility
            message = GeminiChatMessage(response, usage_metadata)
            
            return AIMessage(content=message.content, tool_calls=message.tool_calls, usage_metadata=usage_metadata)
        
        except Exception as e:
            logger.error(f"Error calling Gemini API: {e}")
            # Return a failure message in the same format
            return AIMessage(
                content=f"Error: Failed to generate a response from Gemini. {str(e)}",
                tool_calls=[],
            )
    
    def _convert_to_genai_format(message: BaseMessage) -> types.Content:
        """Convert a langchain message to the format expected by Google Generative AI."""

        if isinstance(message, HumanMessage):
            return types.Content(role="user", parts=[types.Part(text=message.content)])
        elif isinstance(message, AIMessage):
            # Check if the message has tool calls to include
            parts = [types.Part(text=message.content)]
            return types.Content(role="model", parts=parts)
        elif isinstance(message, ToolMessage):
            # For tool messages, create a function response
            return types.Content(
                role="function", 
                parts=[types.Part.from_function_response(
                    name=getattr(message, "name", "tool_function"),
                    response={"result": message.content}
                )]
            )
        elif isinstance(message, SystemMessage):
            return types.Content(role="system", parts=[types.Part(text=message.content)])
        else:
            # Default case for other message types
            return types.Content(role="user", parts=[types.Part(text=str(message.content))])
        


llms = Union[GoogleGenAiWrapperLLM]
