import redis.asyncio as redis
import os
import logging
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)
_client: redis.Redis | None = None


async def _build_client() -> redis.Redis:
    """Build Redis client using TCP connection."""
    try:
        redis_url = os.getenv("REDIS_URL")
        if not redis_url:
            raise ValueError("REDIS_URL environment variable not set")
        
        logger.info(f"Connecting to Redis via TCP...")
        return redis.from_url(
            redis_url,
            decode_responses=True
        )
    except Exception as e:
        logger.error(f"Error initializing Redis client: {e}")
        raise

async def get_redis() -> redis.Redis:
    """Get Redis client instance asynchronously."""
    global _client
    if _client is None:
        _client = await _build_client()
    return _client

async def close_redis():
    global _client
    if _client is not None:
        try:
            await _client.close()
        except Exception as e:
            print(f"Error closing Redis connection: {e}")
        _client = None

async def test():
    import time
    global _client
    if _client is None:
        _client = await _build_client()
    start = time.time()
    pong = await _client.ping()
    print(f"Ping response: {pong}")
    print(f"Time took: {time.time()-start} seconds")

if __name__ == "__main__":
    import asyncio
    asyncio.run(test())