import redis.asyncio as redis
import os
import logging
from dotenv import load_dotenv
from upstash_redis import Redis as UpstashRedis

load_dotenv()

logger = logging.getLogger(__name__)
_client: redis.Redis | None = None


def _build_client() -> redis.Redis:
    """Build Redis client based on environment."""
    if os.getenv("SERVERLESS", "false").lower() == "true":
        logger.info("Connecting to Upstash Redis...")
        try:
            return UpstashRedis(
                url=os.getenv("UPSTASH_REDIS_REST_URL"),
                token=os.getenv("UPSTASH_REDIS_REST_TOKEN")
            )
        except Exception as e:
            logger.error(f"Error initializing Upstash Redis client: {e}")
            raise
    else:
        try:
            return redis.from_url(
                os.getenv("REDIS_URL"),
                decode_responses=True
            )
        except Exception as e:
            logger.error(f"Error initializing Redis client: {e}")
            raise

def get_redis() -> redis.Redis:
    """Get Redis client instance asynchronously."""
    global _client
    if _client is None:
        _client = _build_client()
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
        _client = _build_client()
    start = time.time()
    pong = await _client.ping()
    print(f"Ping response: {pong}")
    print(f"Time took: {time.time()-start} seconds")

if __name__ == "__main__":
    import asyncio
    asyncio.run(test())