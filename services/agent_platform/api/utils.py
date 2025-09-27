from fastapi import Body, Query, Request, HTTPException, status, Path
import base64
import json
from typing import Optional, Any
import uuid


def _b64url_decode(segment: str) -> bytes:
    """Decode a base64url segment (no padding) used in JWTs."""
    padding = "=" * (-len(segment) % 4)
    return base64.urlsafe_b64decode(segment + padding)


def _extract_bearer_token(request: Request) -> Optional[str]:
    """Return the JWT from headers if present.

    Prefers 'x-supabase-access-token' (when proxied), otherwise falls back to
    'Authorization: Bearer <token>'.
    """
    token = request.headers.get("x-supabase-access-token")
    if token:
        return token.strip()

    auth = request.headers.get("authorization") or request.headers.get("Authorization")
    if auth and auth.lower().startswith("bearer "):
        return auth.split(" ", 1)[1].strip()
    return None


async def authenticate_user(request: Request) -> str:
    """Dependency to authenticate the request and return the Supabase user_id.

    - Extracts a Supabase JWT from headers
    - Decodes payload (no signature verification for now)
    - Returns the `sub` claim (user UUID) as a string
    - Raises 401 if missing/invalid
    - Sets the PostgREST client to use this JWT so RLS applies downstream
    """
    # FIXME: verify the token first using supabase client.
    token = _extract_bearer_token(request)
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing Authorization token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Decode JWT payload to get `sub` claim (user id)
    try:
        parts = token.split(".")
        if len(parts) < 2:
            raise ValueError("Malformed JWT")
        payload_raw = _b64url_decode(parts[1])
        payload = json.loads(payload_raw.decode("utf-8"))
        sub = payload.get("sub")
        if not sub:
            raise ValueError("JWT missing 'sub' claim")
        # validate UUID format
        user_uuid = str(uuid.UUID(str(sub)))
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Invalid token: {e}",
            headers={"WWW-Authenticate": "Bearer"},
        ) from e

    # Optionally set the user token on the PostgREST client so RLS uses auth.uid()
    try:
        db = DBConnection()
        await db.initialize()
        client = await db.client
        # Some client wrappers expose postgrest.auth; ignore if unavailable
        if hasattr(client, "postgrest") and hasattr(client.postgrest, "auth"):
            client.postgrest.auth(token)
    except Exception:
        # Non-fatal if DB client setup differs; route handlers can set auth per-request
        pass

    return user_uuid
