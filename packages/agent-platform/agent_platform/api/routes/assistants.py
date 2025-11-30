from fastapi import APIRouter, Body, Depends, HTTPException, Path
from typing import Optional, Dict, Any, List
from pydantic import BaseModel, Field
from ...schema import AssistantSearchRequest, Assistant
from ...graph import get_graph
from ...utils import state_jsonschema, get_configurable_jsonschema
from ..utils import authenticate_user, get_user_optional
from ..services.assistants import Assistants
import logging

logger = logging.getLogger("assistants")
assistants_router = APIRouter(prefix="/assistants")


@assistants_router.post("/search")
async def search_assistants(
    body: AssistantSearchRequest = Body(...),
    user_id: Optional[str] = Depends(get_user_optional),
):
    """Search for assistants. This endpoint also functions as the endpoint to list all assistants."""
    try:
        assistants, cursor = await Assistants.search(
            user_id=user_id,
            graph_id=body.get("graph_id", None),
            metadata=body.get("metadata", {}),
            limit=body.get("limit", 10),
            offset=body.get("offset", 0),
            sort_by=body.get("sort_by", None),
            sort_order=body.get("sort_order", None),
            select=body.get("select", None),
        )
        return assistants
    except Exception as e:
        logger.error(f"Error searching assistants: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Internal server error while searching assistants"
        )


@assistants_router.get("/{assistant_id}")
async def get_assistant(
    assistant_id: str = Path(..., description="The ID of the assistant"),
    user_id: str = Depends(authenticate_user),
):
    """Get an assistant by ID."""
    try:
        assistant = await Assistants.get(assistant_id, user_id)
        
        if not assistant:
            raise HTTPException(
                status_code=404,
                detail=f"Assistant {assistant_id} not found"
            )
        
        return assistant
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching assistant {assistant_id}: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Internal server error while fetching assistant"
        )


@assistants_router.get("/{assistant_id}/schemas")
async def get_assistant_schemas(
    assistant_id: str = Path(..., description="The ID of the assistant"),
    user_id: str = Depends(authenticate_user),
):
    """Get the input/output/state/config schemas for an assistant."""
    try:
        # Get the assistant first to verify it exists
        assistant = await Assistants.get(assistant_id, user_id)
        
        if not assistant:
            raise HTTPException(
                status_code=404,
                detail=f"Assistant {assistant_id} not found"
            )
        
        # Get the graph_id from the assistant
        graph_id = assistant.get("graph_id")
        if not graph_id:
            raise HTTPException(
                status_code=400,
                detail=f"Assistant {assistant_id} has no graph_id"
            )
        
        graph = await get_graph(graph_id)
            
        return {
            "graph_id": graph_id,
            "input_schema": graph.get_input_jsonschema(),
            "output_schema": graph.get_output_jsonschema(),
            "state_schema": state_jsonschema(graph),
            "config_schema": get_configurable_jsonschema(graph),
            "context_schema": graph.get_context_jsonschema(),
        }
        
    except HTTPException:
        raise
    
    except Exception as e:
        logger.error(f"Error fetching schemas for assistant {assistant_id}: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Internal server error while fetching assistant schemas"
        )


@assistants_router.post("")
async def create_assistant(
    body: Dict[str, Any] = Body(...),
    user_id: str = Depends(authenticate_user),
):
    """Create a new assistant."""
    try:
        # Extract fields from body
        assistant_id = body.get("assistant_id")
        graph_id = body.get("graph_id")
        name = body.get("name")
        
        if not graph_id:
            raise HTTPException(
                status_code=400,
                detail="graph_id is required"
            )
        
        if not name:
            raise HTTPException(
                status_code=400,
                detail="name is required"
            )
        
        assistant = await Assistants.put(
            assistant_id=assistant_id or str(__import__('uuid').uuid4()),
            user_id=user_id,
            graph_id=graph_id,
            config=body.get("config", {}),
            context=body.get("context", {}),
            metadata=body.get("metadata", {}),
            if_exists=body.get("if_exists", "raise"),
            name=name,
            description=body.get("description"),
        )
        
        return assistant
    
    except HTTPException:
        raise
    
    except Exception as e:
        logger.error(f"Error creating assistant: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Internal server error while creating assistant"
        )


@assistants_router.patch("/{assistant_id}")
async def patch_assistant(
    assistant_id: str = Path(..., description="The ID of the assistant"),
    body: Dict[str, Any] = Body(...),
    user_id: str = Depends(authenticate_user),
):
    """Update an assistant."""
    try:
        assistant = await Assistants.patch(
            assistant_id=assistant_id,
            user_id=user_id,
            config=body.get("config"),
            context=body.get("context"),
            graph_id=body.get("graph_id"),
            metadata=body.get("metadata"),
            name=body.get("name"),
            description=body.get("description"),
        )
        
        return assistant
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating assistant {assistant_id}: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Internal server error while updating assistant"
        )


@assistants_router.delete("/{assistant_id}")
async def delete_assistant(
    assistant_id: str = Path(..., description="The ID of the assistant"),
    user_id: str = Depends(authenticate_user),
):
    """Delete an assistant by ID."""
    try:
        await Assistants.delete(assistant_id, user_id)
    
    except HTTPException:
        raise
    
    except Exception as e:
        logger.error(f"Error deleting assistant {assistant_id}: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Internal server error while deleting assistant"
        )
