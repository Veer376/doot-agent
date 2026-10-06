import asyncio
import time
import urllib.error
import urllib.request
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route

from .diagnostics import (
    RUNTIME_INSTANCE_ID,
    RUNTIME_STARTED_AT,
    STORE,
    DiagnosticContext,
    classify_failure,
    record_event,
)
from .config import load_settings
from .workspaces import register_workspace, workspace_catalog
from .permissions import permission_settings, set_default_mode, revoke_grant


def _probe(url: str) -> dict:
    started = time.monotonic()
    try:
        with urllib.request.urlopen(url, timeout=4) as response:
            body = response.read(4096).decode("utf-8", errors="replace")
            return {
                "ok": 200 <= response.status < 400,
                "status": response.status,
                "latency_ms": round((time.monotonic() - started) * 1000, 2),
                "body": body[:1000],
            }
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        return {
            "ok": False,
            "status": None,
            "latency_ms": round((time.monotonic() - started) * 1000, 2),
            "error": str(exc),
        }


async def _component_health() -> dict:
    settings = load_settings()
    return {
        "model_proxy": await asyncio.to_thread(
            _probe, f"{settings.proxy_url.rstrip('/')}/health"
        )
    }


async def workspaces(request: Request):
    try:
        catalog = await workspace_catalog()
        if request.method == "POST":
            body = await request.json()
            path = body.get("path")
            if not isinstance(path, str) or not path.strip():
                return JSONResponse({"error": "Enter a workspace directory"}, status_code=400)
            selected = await register_workspace(path)
            return JSONResponse({"path": selected, "name": selected.rstrip("/").split("/")[-1]})
        return JSONResponse({"projects": catalog.get("savedProjects", []), "roots": catalog.get("authorizedProjectRoots", [])})
    except (ValueError, FileNotFoundError, NotADirectoryError) as exc:
        return JSONResponse({"error": str(exc)}, status_code=400)
    except Exception:
        return JSONResponse({"error": "Workspace service is unavailable"}, status_code=503)


async def permissions(request: Request):
    try:
        if request.method == "PATCH":
            body = await request.json()
            await asyncio.to_thread(set_default_mode, body.get("default_mode"))
        elif request.method == "DELETE":
            body = await request.json()
            await asyncio.to_thread(revoke_grant, body["workspace"], body["scope"], body["operation"])
        return JSONResponse(await asyncio.to_thread(permission_settings))
    except (ValueError, KeyError, TypeError) as exc:
        return JSONResponse({"error": str(exc)}, status_code=400)


async def diagnostics_events(request: Request):
    if request.method == "POST":
        try:
            body = await request.json()
            context = DiagnosticContext(
                thread_id=body.get("thread_id") or None,
                run_id=body.get("run_id") or None,
                task_id=body.get("task_id") or None,
            )
            event_id = await asyncio.to_thread(
                record_event,
                str(body.get("kind") or "client.event"),
                source="frontend",
                severity=str(body.get("severity") or "info"),
                context=context,
                component=str(body.get("component") or "frontend"),
                message=body.get("message"),
                details=body.get("details") or {},
            )
            return JSONResponse({"ok": True, "event_id": event_id})
        except (TypeError, ValueError) as exc:
            return JSONResponse({"error": str(exc)}, status_code=400)

    thread_id = request.query_params.get("thread_id") or None
    run_id = request.query_params.get("run_id") or None
    try:
        limit = int(request.query_params.get("limit", "200"))
    except ValueError:
        limit = 200
    return JSONResponse(
        {
            "runtime_instance_id": RUNTIME_INSTANCE_ID,
            "events": await asyncio.to_thread(
                STORE.events, thread_id=thread_id, run_id=run_id, limit=limit
            ),
        }
    )


async def diagnostics_analyze(request: Request):
    try:
        body = await request.json()
    except Exception:
        body = {}
    thread_id = body.get("thread_id") or None
    run_id = body.get("run_id") or None
    raw_error = body.get("error") or "Unknown stream failure"
    await asyncio.to_thread(
        record_event,
        "stream.error.reported",
        source="frontend",
        severity="error",
        context=DiagnosticContext(thread_id=thread_id, run_id=run_id),
        component="stream",
        message=str(raw_error),
        details={
            "phase": body.get("phase"),
            "client": body.get("client") or {},
        },
    )
    analysis = await asyncio.to_thread(
        classify_failure, raw_error, thread_id=thread_id, run_id=run_id
    )
    components = await _component_health()
    proxy = components["model_proxy"]
    if not proxy.get("ok") and analysis["code"] == "stream_failure":
        analysis.update(
            {
                "code": "model_proxy_unavailable",
                "title": "Model proxy unavailable",
                "message": (
                    "Doot could not reach the local Antigravity model proxy. "
                    "Start or repair the proxy, then retry the run."
                ),
                "retryable": True,
            }
        )
    analysis["components"] = components
    return JSONResponse(analysis)


async def diagnostics_health(request: Request):
    components = await _component_health()
    return JSONResponse(
        {
            "ok": all(component.get("ok") for component in components.values()),
            "runtime_instance_id": RUNTIME_INSTANCE_ID,
            "runtime_started_at": RUNTIME_STARTED_AT,
            "database": str(STORE.path),
            "components": components,
        }
    )


app = Starlette(routes=[
    Route("/workspaces", workspaces, methods=["GET", "POST"]),
    Route("/permissions", permissions, methods=["GET", "PATCH", "DELETE"]),
    Route("/diagnostics", diagnostics_events, methods=["GET", "POST"]),
    Route("/diagnostics/analyze", diagnostics_analyze, methods=["POST"]),
    Route("/diagnostics/health", diagnostics_health, methods=["GET"]),
])
