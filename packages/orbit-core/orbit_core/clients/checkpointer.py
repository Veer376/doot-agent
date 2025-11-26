"""PostgreSQL-based async checkpointer for LangGraph.

This module provides a singleton checkpointer instance that persists for the application lifetime.
Initialize with setup_checkpointer() at app startup and cleanup with close_checkpointer() at shutdown.
"""
import logging
import os
from typing import Optional

from psycopg_pool import AsyncConnectionPool
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.checkpoint.memory import InMemorySaver
logger = logging.getLogger("checkpointer")


# Singleton instances
_checkpointer_instance: Optional[BaseCheckpointSaver] = None
_connection_pool: Optional[AsyncConnectionPool] = None


async def setup_checkpointer(connection_string: Optional[str] = None) -> BaseCheckpointSaver:
    """Initialize the PostgreSQL checkpointer singleton.
    
    Should be called once at application startup (e.g., in FastAPI lifespan).
    
    Args:
        connection_string: Optional connection string. Uses POSTGRES_URL env var if not provided.
        
    Returns:
        Initialized AsyncPostgresSaver instance
    """    
    global _checkpointer_instance, _connection_pool
    
    if _checkpointer_instance is not None:
        logger.info("✅ Checkpointer already initialized, returning existing instance")
        return _checkpointer_instance
    
    conn_str = connection_string or os.getenv("POSTGRES_URL")
    
    if not conn_str:
        raise ValueError("POSTGRES_URL environment variable not set")
    
    # Create psycopg connection pool with shorter idle timeout to prevent stale connections
    _connection_pool = AsyncConnectionPool(
        conn_str,
        min_size=1,  # Reduce minimum connections
        max_size=20,
        max_waiting=20,
        max_lifetime=1800,  # 30 minutes (shorter than server timeout)
        max_idle=300,  # 5 minutes (prevent idle connection timeouts)
        reconnect_timeout=30,
        open=False,
        kwargs={
            "autocommit": True, 
            "prepare_threshold": None,  # Disable prepared statements for transaction pooler
        },
        check=AsyncConnectionPool.check_connection  # Validate connections before use
    )
    
    # Open the pool
    await _connection_pool.open()
    
    # Create checkpointer with the pool directly
    # AsyncPostgresSaver accepts either AsyncConnection or AsyncConnectionPool
    _checkpointer_instance = AsyncPostgresSaver(_connection_pool)
    
    # Setup the database tables
    await _checkpointer_instance.setup()
    
    logger.info("✅ PostgreSQL checkpointer initialized and ready")
    
    return _checkpointer_instance


def get_checkpointer() -> BaseCheckpointSaver:
    """Get the checkpointer instance.
    
    Returns:
        The initialized checkpointer instance
        
    Raises:
        RuntimeError: If checkpointer hasn't been initialized with setup_checkpointer()
    """
    if _checkpointer_instance is None:
        raise RuntimeError(
            "Checkpointer not initialized. Call setup_checkpointer() first, "
            "typically in your FastAPI lifespan context."
        )
    
    return _checkpointer_instance


async def close_checkpointer() -> None:
    """Close the PostgreSQL checkpointer singleton.
    
    Should be called at application shutdown (e.g., in FastAPI lifespan).
    """
    global _checkpointer_instance, _connection_pool
    
    if _connection_pool:
        await _connection_pool.close()
        _connection_pool = None
        logger.info("✅ PostgreSQL connection pool closed")
    
    if _checkpointer_instance:
        _checkpointer_instance = None
        logger.info("✅ PostgreSQL checkpointer closed")
