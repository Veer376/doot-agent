from fastapi import APIRouter, Body
from typing import Optional, Dict, Any, List
from pydantic import BaseModel, Field
from ...schema import AssistantSearchRequest, Assistant
from ...config import default_assistants
from ...graph import get_graph
from ...utils import state_jsonschema, get_configurable_jsonschema


assistants_router = APIRouter(prefix="/assistants")


class AssistantSearch(BaseModel):
    """Schema for searching assistants."""

    graph_id: Optional[str] = Field(None, description="Graph ID to filter by")
    metadata: Optional[Dict[str, Any]] = Field(
        None, description="Metadata to filter by"
    )
    limit: Optional[int] = Field(10, description="Maximum number of results to return")
    offset: Optional[int] = Field(0, description="Number of results to skip")


@assistants_router.post(
    "/search", 
    summary="Search for assistants", 
    tags=["assistants"])
async def search_assistants(
    # user_id: str = Depends(authenticate_user)
    body: AssistantSearchRequest = Body(...),
):
    """Search for assistants. This endpoint also functions as the endpoint to list all assistants."""
    try:
        assistants: list[Assistant] = list(default_assistants.values())
    except Exception as e:
        print(f"Error loading default assistants: {e}")
        assistants = []

    return assistants


@assistants_router.get(
    "/{assistant_id}", summary="Get assistant by ID", tags=["assistants"]
)
async def get_assistant(
    assistant_id: str,
):
    """
    Get an assistant by ID. This is a minimal implementation that returns a dummy assistant.
    """
    # directly search on the supabase for the assistant_id


@assistants_router.get(
    "/{assistant_id}/schemas",
    summary="Get an assistant by ID",
    tags=["assistants"]
)
async def get_assistant_schemas(
    assistant_id: str,
):
    graph_id = default_assistants.get(assistant_id).graph_id
    graph = await get_graph(graph_id)
        
    return {
        "graph_id": graph_id,
        "input_schema": graph.get_input_jsonschema(),
        "output_schema": graph.get_output_jsonschema(),
        "state_schema": state_jsonschema(graph),
        "config_schema": get_configurable_jsonschema(graph),
        "context_schema": graph.get_context_jsonschema(),
    }
    
@assistants_router.post(
  '',
  summary="Create a new assistant",
)
async def create_assistant(
  body: Dict[str, Any] = Body(...),
):
    """
    Create a new assistant. This is a minimal implementation that echoes back the input body.
    """
    print(f"Assistant.create.body: {body}")
    
    return {}