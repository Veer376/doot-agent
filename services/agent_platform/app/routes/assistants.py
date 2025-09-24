from fastapi import APIRouter, Body
from typing import Optional, Dict, Any, List
from pydantic import BaseModel, Field

assistants_router = APIRouter()


class AssistantSearch(BaseModel):
    """Schema for searching assistants."""

    graph_id: Optional[str] = Field(None, description="Graph ID to filter by")
    metadata: Optional[Dict[str, Any]] = Field(
        None, description="Metadata to filter by"
    )
    limit: Optional[int] = Field(10, description="Maximum number of results to return")
    offset: Optional[int] = Field(0, description="Number of results to skip")


@assistants_router.post("/search", summary="Search for assistants", tags=["assistants"])
async def search_assistants(
    body: Optional[AssistantSearch] = Body(None),
):
    """
    Search for assistants. This is a minimal implementation that returns a dummy assistant
    since we're focusing on direct runs rather than assistant management.
    """
    # Return a single dummy assistant as an array directly
    assistant_id = body.graph_id if body and body.graph_id else "default_assistant"

    return [
        {
            "assistant_id": assistant_id,
            "graph_id": assistant_id,
            "name": "Default Assistant",
            "description": "A minimal assistant implementation for direct runs",
            "metadata": {},
            "created_at": "2025-09-17T00:00:00Z",
            "updated_at": "2025-09-17T00:00:00Z",
        }
    ]


@assistants_router.get(
    "/{assistant_id}", summary="Get assistant by ID", tags=["assistants"]
)
async def get_assistant(
    assistant_id: str,
):
    """
    Get an assistant by ID. This is a minimal implementation that returns a dummy assistant.
    """
    return {
        "assistant_id": assistant_id,
        "graph_id": assistant_id,
        "name": "Default Assistant",
        "description": "A minimal assistant implementation for direct runs",
        "metadata": {},
        "created_at": "2025-09-17T00:00:00Z",
        "updated_at": "2025-09-17T00:00:00Z",
    }
