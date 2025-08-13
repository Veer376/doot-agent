from typing import Literal, Optional
from pydantic import BaseModel, Field
from langchain.chat_models import init_chat_model

# Defines the high-level goal of the extraction, making it semantically clear.
ExtractionGoal = Literal[
    "MAIN_CONTENT",      # For reading the core article of a page
    "SINGLE_ITEM",       # For a single piece of text, like a price or phone number
    "LIST_OF_ITEMS",     # For a list of similar things, like prices, names, or comments
    # "TABLE"              # For structured table data
]

class ExtractionPlan(BaseModel):
    goal: ExtractionGoal = Field(
        ..., 
        description="The primary goal of the extraction, determining how the result should be processed."
    )
    selector: Optional[str] = Field(
        None, 
        description="The CSS selector to locate the target element(s). Should be null if the goal is 'MAIN_CONTENT'."
    )
    
from langchain_core.messages import SystemMessage, HumanMessage
from langchain_core.language_models import BaseChatModel

async def get_extraction_plan(
    query: str, 
    dom: str, 
    element_index: int | None = None,
    element_description: str | None = None,
) -> ExtractionPlan:
    """
    Invokes a specialized "strategist" LLM to create a detailed extraction plan.

    Args:
        task: The user's original, high-level task.
        query: The agent's immediate extraction query.
        dom: The simplified DOM of the current viewport.
        llm: The LangChain chat model instance to use.

    Returns:
        An ExtractionPlan object with the determined goal and selector.
    """
    # This persona is token-efficient but sets a clear, expert role.
    system_message = (
        "You are an expert web data analyst. Your sole purpose is to analyze a simplified DOM structure "
        "and create a precise JSON plan to extract requested information. You must choose the best goal "
        "and provide the most accurate CSS selector possible."
    )
    
    # Build the prompt dynamically
    prompt_parts = [
        "Based on the user's query, create a JSON extraction plan."
    ]

    if element_index is not None and element_description:
        # This is the "Query by Example" path
        prompt_parts.append(
            "The user has provided an example element. Your goal is to find the best selector for ALL similar items on the page."
        )
        prompt_parts.append(f"Example Element Index: {element_index}")
        prompt_parts.append(f"Example Element Description: \"{element_description}\"")
        prompt_parts.append(f"Contextual DOM Snippet:\n---\n{dom}")
    else:
        # This is the "Discovery" path
        prompt_parts.append(
            "The user wants to find something on the page. Your goal is to find the best selector for the requested content."
        )
        prompt_parts.append(f"Simplified DOM of Viewport:\n---\n{dom}")

    prompt_parts.append(f"\nUser Query: \"{query}\"")

    # Join all parts into the final prompt
    prompt = "\n".join(prompt_parts)

    llm = init_chat_model("google_genai:gemini-2.5-flash")
    # Chain the structured output schema to the LLM
    extraction_llm = llm.with_structured_output(schema=ExtractionPlan)
    
    # Invoke the LLM with the system and user messages
    messages = [
        SystemMessage(content=system_message),
        HumanMessage(content=prompt)
    ]
    
    plan = await extraction_llm.ainvoke(messages)
    
    return plan
    