from typing import Optional
from supabase import create_async_client, AsyncClient
import logging
import os
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger("supabase_client")

_client: AsyncClient | None = None

async def _build_client() -> AsyncClient:
    
    if os.getenv("DOOT_LOCAL_MODE") == "true":
        from postgrest import AsyncPostgrestClient
        from urllib.parse import urlparse
        url = os.environ["POSTGREST_URL"]
        if urlparse(url).hostname not in {"127.0.0.1", "localhost", "::1", "postgrest"}:
            raise ValueError("Local profile requires a local PostgREST service")
        return AsyncPostgrestClient(url)
    supabase_url = os.getenv("SUPABASE_URL")
    supabase_key = os.getenv("SUPABASE_SERVICE_ROLE_KEY") or os.getenv("SUPABASE_ANON_KEY")

    if not supabase_url or not supabase_key:
        logger.error("Missing required environment variables for Supabase connection")
        raise RuntimeError("SUPABASE_URL and a key (SERVICE_ROLE_KEY or ANON_KEY) environment variables must be set.")

    logger.debug("Building new Supabase client")

    client = await create_async_client(
        supabase_url,
        supabase_key,
    )

    return client

async def get_supabase() -> AsyncClient:
    global _client
    if _client is None:
        _client = await _build_client()
    return _client

async def close_supabase():
    global _client
    if _client is not None:
        try:
            if hasattr(_client, "aclose"):
                await _client.aclose()
            elif hasattr(_client, "close"):
                await _client.close()
        except Exception as e:
            logger.error(f"Error closing Supabase connection: {e}")
        _client = None
        
async def test():
    client = await get_supabase()
    result = await client.table("threads").select("*").execute()
    if getattr(result, "error", None):
        # result.error can be None or an object depending on client version
        raise RuntimeError(f"Error fetching threads: {getattr(result.error, 'message', result.error)}")
    print(f"Threads: {result.data}")

if __name__ == "__main__":
    import asyncio
    asyncio.run(test())