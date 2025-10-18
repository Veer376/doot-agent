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
from .routes.threads import threads_router
from .routes.assistants import assistants_router
from orbit_core.utils.logging_config import setup_logging
from contextlib import asynccontextmanager
from orbit_core.clients import get_supabase, close_supabase, get_redis, close_redis
from ..graph import load_graphs_from_file, GraphRegistryError

# Ensure asyncio subprocess support on Windows for Playwright by using the Selector policy
# Must be set at import time before any event loop is created (e.g., before uvicorn starts)
if sys.platform == "win32" and hasattr(asyncio, "WindowsSelectorEventLoopPolicy"):
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

logger = logging.getLogger("agent_platform")

# Define the project root where langgraph.json lives
# In Docker: /orbit-agent (via mount)
# Can be overridden via ORBIT_AGENT_ROOT environment variable
PROJECT_ROOT = Path(os.getenv("ORBIT_AGENT_ROOT", "/orbit-agent"))


@asynccontextmanager
async def lifespan(app: FastAPI):
    # startup logic
    try:
        load_graphs_from_file(root=PROJECT_ROOT)
        logger.info("Graph registry warmed with graph(s)")
    except GraphRegistryError as exc:
        logger.error("Failed to initialise graph registry: %s", exc)
        raise
    except Exception as exc:
        logger.error("Unexpected error during graph registry init: %s", exc)
        pass

    await get_supabase()
    await get_redis()

    yield

    # shutdown logic
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
    allow_origins=["*"],  # Allows all origins
    allow_credentials=True,
    allow_methods=["*"],  # Allows all methods
    allow_headers=["*"],  # Allows all headers
)


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
        "agent_platform.app.api.main:app",
        host="0.0.0.0",
        port=5000,
        reload=False if sys.platform == "win32" else True,
        reload_delay=5,
        loop="asyncio",  # Use asyncio loop instead of uvloop for Windows subprocess support
    )
