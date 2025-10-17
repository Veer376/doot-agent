import redis.asyncio as redis
import os
from dotenv import load_dotenv
load_dotenv()

_client: redis.Redis | None = None

def _build_client() -> redis.Redis:
    
    url = os.getenv("REDIS_URL")
    if url:
        return redis.from_url(
            url,
            decode_responses=True,
            health_check_interval=30,
            retry_on_timeout=True,
        )
    
    # NOTE: Avoid hardcoding credentials in source. Prefer REDIS_URL or env vars.
    redis_kwargs = {}
    
    if os.getenv("IN_DOCKER", "false").lower() == "true":
        redis_kwargs['host'] = '127.0.0.1'
        redis_kwargs['port'] = 6379
        
    else:
        redis_kwargs['host'] = 'redis-10032.c10.us-east-1-4.ec2.redns.redis-cloud.com'
        redis_kwargs['port'] = 10032
        redis_kwargs['username'] = 'default'
        redis_kwargs['password'] = 'REMOVED_CREDENTIAL'
        
    redis_kwargs['decode_responses'] = True
    
    return redis.Redis(**redis_kwargs)

def get_redis() -> redis.Redis:
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