import os
import uuid
from typing import Any, Dict, List, Optional, Union, Generator
from dotenv import load_dotenv
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, BaseMessage
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser
from langchain.chat_models import init_chat_model
from typing import Callable, TypeVar, Generic
from .types import MessagePlanBase, LLMConfig
from .types import LLM
from .usage_stats import get_usage_stats
from langchain_google_genai import ChatGoogleGenerativeAI


class LangChainLLM(LLM):
    """Wrapper for LangChain to provide a consistent interface for different LLM providers."""

    def __init__(self, model_name: str = None, provider: str = None):
        """Initialize the LangChain wrapper."""
        super().__init__(model_name, provider)

    async def __call__(
        self,
        messages: MessagePlanBase|list[BaseMessage],
        tools: list[Callable]|None = None,
        config: LLMConfig = None,
    ) -> AIMessage:
        """Get a response from langgraph LLM."""

        # Instead of concatenating provider and model name, pass them separately
        model = init_chat_model(self.model_name, model_provider=self.provider)
        
        if isinstance(messages, MessagePlanBase):
            messages = messages.to_langchain()

        # We're ignoring the config parameter for now since LangChain doesn't need it
        # but we keep it in the method signature for compatibility with the LLM interface
        if tools:
            response = await model.bind_tools(tools).ainvoke(messages)
        else: 
            response = await model.ainvoke(messages)
            
        # Track usage statistics
        usage_stats = get_usage_stats()
        if hasattr(response, "usage_metadata") and response.usage_metadata:
            usage_stats.update_from_langgraph(self.model_name, response.usage_metadata)

        return response
