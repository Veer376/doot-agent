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
from .routes.webrtc import webrtc_router
from orbit_core.utils.logging_config import setup_logging
from contextlib import asynccontextmanager
from orbit_core.clients import get_supabase, close_supabase, get_redis, close_redis
from orbit_core.clients.checkpointer import setup_checkpointer, close_checkpointer
from ..graph import load_graphs_from_file, GraphRegistryError
from ..browser_registry import browser_registry

"""Main FastAPI application entrypoint.

Important Windows note:
Playwright launches a helper process. On Windows, only the Proactor event loop supports
asyncio subprocess APIs. If you force the Selector loop (WindowsSelectorEventLoopPolicy)
you will get `NotImplementedError` from `_make_subprocess_transport` when Playwright
attempts to start.

So we explicitly set the Proactor policy early, before any loop is created.
"""

if sys.platform == "win32":
    try:
        asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
    except AttributeError:
        # Fallback: older Python versions (<3.8) might not have Proactor policy
        pass

logger = logging.getLogger("agent_platform")

# Define the project root where langgraph.json lives
# In Docker: /orbit-agent (via mount)
# In development: defaults to current working directory
# Can be overridden via ORBIT_AGENT_ROOT environment variable
default_root = Path.cwd() if not os.getenv("ORBIT_AGENT_ROOT") else Path(os.getenv("ORBIT_AGENT_ROOT"))
PROJECT_ROOT = Path(os.getenv("ORBIT_AGENT_ROOT", default_root))


@asynccontextmanager
async def lifespan(app: FastAPI):
    # startup logic - initialize clients first
    await get_supabase()
    await get_redis()
    await setup_checkpointer()

    # Then load graphs (which depend on checkpointer being initialized)
    try:
        load_graphs_from_file(root=PROJECT_ROOT)
        logger.info("Graph registry warmed with graph(s)")
    except GraphRegistryError as exc:
        logger.error("Failed to initialise graph registry: %s", exc)
        raise
    except Exception as exc:
        logger.error("Unexpected error during graph registry init: %s", exc)
        pass

    # Initialize a test browser session
    # Use BROWSER_WSS_URL from env, default to localhost:3500 for development
    browser_wss_url = os.environ.get("BROWSER_WSS_URL", "ws://localhost:3500")
    logger.info(f"Initializing test browser session (WSS: {browser_wss_url})")
    
    # Explicitly set the WSS URL in the registry
    browser_registry.set_wss_url(browser_wss_url)
    
    try:
        await browser_registry.create_session("test_user", initial_url="https://www.google.com")
        logger.info("Test browser session created successfully")
    except Exception as exc:
        logger.error(f"Failed to create test browser session: {exc}")
        # Don't fail startup, just log the error
    
    yield

    # shutdown logic
    await browser_registry.close_all()
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
app.include_router(webrtc_router)

# Main startup
if __name__ == "__main__":
    uvicorn.run(
        "agent_platform.api.main:app",
        host="0.0.0.0",
        port=5000,
        reload=False if sys.platform == "win32" else True,
        reload_delay=5,
        loop="asyncio",  # Use asyncio loop instead of uvloop for Windows subprocess support
    )
