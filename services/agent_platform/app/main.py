from fastapi import FastAPI, Depends
from fastapi.middleware.cors import CORSMiddleware
from typing import Dict
import logging
import time
import datetime
import uvicorn
from .routes.threads import threads
from .routes.assistants import assistants_router
from core.utils.logging_config import setup_logging
from contextlib import asynccontextmanager
from core.clients import get_supabase, close_supabase, get_redis, close_redis

logger = logging.getLogger("agent_platform")

@asynccontextmanager
async def lifespan(app: FastAPI):
    # startup logic
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


# Health check endpoint
@app.get("/", response_model=Dict[str, str])
async def health_check():
    """
    Health check endpoint to verify if the server is running properly
    """
    return {
        "status": "ok",
        "timestamp": datetime.datetime.now().isoformat(),
        "service": "orbit-agent-api",
    }


@app.get("/info")
async def get_info():
    """
    LangGraph SDK compatibility endpoint to get basic API info.
    """
    return {
        "service": "orbit-agent-api",
        "version": "0.1.0",
        "langgraph_schema_version": "0.1.0",
    }


app.include_router(threads, prefix="/threads", tags=["threads"])
app.include_router(assistants_router, prefix="/assistants", tags=["assistants"])

# Main startup
if __name__ == "__main__":
    # When running as a module (python -m app.main), uvicorn should import via the package path
    uvicorn.run("app.main:app", host="0.0.0.0", port=5000, reload=True, reload_delay=5)
