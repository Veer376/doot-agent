from fastapi import FastAPI, Depends
from fastapi.middleware.cors import CORSMiddleware
from typing import Dict
import logging
import time
import datetime
import uvicorn
import asyncio
import sys
import os
from pathlib import Path
from .routes.runs import runs_router
from .release_threads import router as threads_router
from .routes.assistants import assistants_router
from orbit_core.utils.logging_config import setup_logging
from contextlib import asynccontextmanager
from orbit_core.clients import get_supabase, close_supabase, get_redis, close_redis
from orbit_core.clients.checkpointer import setup_checkpointer, close_checkpointer
from ..graph import load_graphs_from_file, GraphRegistryError
from ..schema import RunCreateStateful, Checkpoint, ThreadStateSearch
from pydantic import TypeAdapter

# Ensure asyncio subprocess support on Windows for Playwright by using the Selector policy
# Must be set at import time before any event loop is created (e.g., before uvicorn starts)
if sys.platform == "win32" and hasattr(asyncio, "WindowsSelectorEventLoopPolicy"):
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

logger = logging.getLogger("agent_platform")

# Define the project root where langgraph.json lives.  We try to be
# clever for convenience:
#
# * In production (docker) the repository is mounted at `/orbit-agent` so
#   the root is fixed by the deployment manifest.
# * In development we normally run from the service directory
#   (`packages/agent-platform`), but the configuration file lives at the
#   repository root.  rather than forcing every developer to set an
#   environment variable, the graph loader now searches parent directories
#   for `langgraph.json` (see ``agent_platform.graph._resolve_config_path``),
#   so the default value is simply the current working directory.  an
#   explicit ``ORBIT_AGENT_ROOT`` may still be provided to override this.
default_root = Path.cwd() if not os.getenv("ORBIT_AGENT_ROOT") else Path(os.getenv("ORBIT_AGENT_ROOT"))
PROJECT_ROOT = Path(os.getenv("ORBIT_AGENT_ROOT", default_root))


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Force Pydantic to rebuild TypeAdapters for TypedDicts with forward references
    TypeAdapter(RunCreateStateful).rebuild()
    TypeAdapter(Checkpoint).rebuild()
    TypeAdapter(ThreadStateSearch).rebuild()
    
    # startup logic - initialize clients first
    await get_supabase()
    await get_redis()
    await setup_checkpointer()

    # Then load graphs (which depend on checkpointer being initialized)
    try:
        load_graphs_from_file(config_path=os.getenv("DOOT_GRAPH_CONFIG", "langgraph.showcase.json"), root=PROJECT_ROOT)
        logger.info("Graph registry warmed with graph(s)")
    except GraphRegistryError as exc:
        logger.error("Failed to initialise graph registry: %s", exc)
        raise
    except Exception as exc:
        logger.error("Unexpected error during graph registry init: %s", exc)
        pass

    yield

    # shutdown logic
    await close_checkpointer()
    await close_supabase()
    await close_redis()


setup_logging()

app = FastAPI(
    title="Orbit Agent API",
    description="API for Orbit Agent",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[os.getenv("DOOT_WEB_ORIGIN", "http://127.0.0.1:3000")],  # Allows all origins
    allow_credentials=True,
    allow_methods=["*"],  # Allows all methods
    allow_headers=["*"],  # Allows all headers
)

# add the app.exception_handler
# use assertion in the project.

# Middleware for request logging
@app.middleware("http")
async def log_requests(request, call_next):
    start_time = time.time()
    response = await call_next(request)
    process_time = time.time() - start_time
    logger.info(
        f"{request.method} {request.url.path} - {response.status_code} - {process_time*100:.4f}ms"
    )
    return response


@app.get("/")
async def health_check():
    """
    Health check endpoint to verify if the server is running properly
    """
    return {
        "status": "ok",
        "timestamp": datetime.datetime.now().isoformat(),
        "service": "orbit-agent-api",
    }

app.include_router(threads_router)
app.include_router(assistants_router)
app.include_router(runs_router)

# Main startup
if __name__ == "__main__":
    uvicorn.run(
        "agent_platform.api.main:app",
        host="127.0.0.1",
        port=5000,
        reload=False if sys.platform == "win32" else True,
        reload_delay=5,
        loop="asyncio",  # Use asyncio loop instead of uvloop for Windows subprocess support
    )

@app.get("/models")
async def models():
    model = os.getenv("DOOT_MODEL", "google_genai:gemini-2.5-flash")
    provider = model.split(":", 1)[0]
    return {"models": [{"id": model, "name": model.split(":",1)[-1], "provider": "google" if provider=="google_genai" else provider, "source": "backend"}]}

@app.post("/diagnostics/events", status_code=204)
async def diagnostic_event():
    # The local graph diagnostics are not part of this profile.
    return None

@app.get("/diagnostics")
async def diagnostics():
    return {"events": [], "enabled": False}
