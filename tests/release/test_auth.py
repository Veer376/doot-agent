from starlette.requests import Request
from fastapi import HTTPException
from agent_platform.api.utils import authenticate_user, LOCAL_USER_ID
import pytest

def request(token):
    headers=[] if token is None else [(b'authorization',('Bearer '+token).encode())]
    return Request({'type':'http','headers':headers})

async def test_local_session_is_explicit(monkeypatch):
    monkeypatch.setenv('DOOT_LOCAL_MODE','true')
    assert await authenticate_user(request('local'))==LOCAL_USER_ID
    for token in [None,'forged.jwt.payload']:
        with pytest.raises(HTTPException):await authenticate_user(request(token))

async def test_missing_hosted_session_rejected(monkeypatch):
    monkeypatch.delenv('DOOT_LOCAL_MODE',raising=False)
    with pytest.raises(HTTPException):await authenticate_user(request(None))
