from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_google_vertexai import ChatVertexAI
from typing import Literal, Callable
from langchain_google_genai._enums import HarmBlockThreshold, HarmCategory
from dataclasses import dataclass, field
from langchain_core.language_models.chat_models import BaseChatModel

types = Literal["gemini", "vertex-ai"]

@dataclass
class GeminiConfig:
    model: str
    temperature: float = 0.8
    max_retries: int = 2
    max_output_tokens: int | None = None
    include_thoughts: bool = True
    thinking_budget: int = -1
    tools: list[dict] = field(default_factory=list)
    safety_settings: dict = field(default_factory=lambda: {
        HarmCategory.HARM_CATEGORY_HARASSMENT: HarmBlockThreshold.BLOCK_NONE,
        HarmCategory.HARM_CATEGORY_HATE_SPEECH: HarmBlockThreshold.BLOCK_NONE,
        HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT: HarmBlockThreshold.BLOCK_NONE,
        HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT: HarmBlockThreshold.BLOCK_NONE,
        HarmCategory.HARM_CATEGORY_CIVIC_INTEGRITY: HarmBlockThreshold.BLOCK_NONE,
    })
    
@dataclass
class VertexAIConfig:
    model: str
    location: str
    project: str
    temperature: float = 0.8
    
    

class LLM:
    def __init__(self, config: GeminiConfig | VertexAIConfig) -> BaseChatModel:
        self.type = type
        
        if isinstance(config, GeminiConfig):
            self.llm = ChatGoogleGenerativeAI(**config.__dict__)
        elif isinstance(config, VertexAIConfig):
            self.llm = ChatVertexAI(**config.__dict__)
        else:
            raise ValueError(f"Unsupported config type: {type(config)}")
    
    def bind_tools(self, tools: list[Callable]) -> BaseChatModel:
        return self.llm.bind_tools(tools)
    
    async def ainvoke(self, *args, **kwargs):
        return await self.llm.ainvoke(*args, **kwargs)
    
    def invoke(self, *args, **kwargs):
        return self.llm.invoke(*args, **kwargs)