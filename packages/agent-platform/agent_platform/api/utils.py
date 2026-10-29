"""Authentication for Supabase deployments and explicit single-user local runs."""
import os
from fastapi import Request, HTTPException
from orbit_core.clients import get_supabase

LOCAL_USER_ID = "00000000-0000-4000-8000-000000000001"

async def authenticate_user(request: Request) -> str:
    token = request.headers.get("x-supabase-access-token")
    auth = request.headers.get("authorization", "")
    if not token and auth.lower().startswith("bearer "):
        token = auth.split(" ", 1)[1]
    if os.getenv("DOOT_LOCAL_MODE") == "true":
        if token != "local":
            raise HTTPException(401, "Local session required")
        return LOCAL_USER_ID
    if not token:
        raise HTTPException(401, "Authentication required")
    try:
        client = await get_supabase()
        result = await client.auth.get_user(token)
        if not result.user:
            raise ValueError("No user")
        return str(result.user.id)
    except Exception:
        raise HTTPException(401, "Invalid session") from None

async def get_user_optional(request: Request) -> str | None:
    try:
        return await authenticate_user(request)
    except HTTPException:
        return None
