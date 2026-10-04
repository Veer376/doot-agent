from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route

from .workspaces import validate_workspace, workspace_catalog


async def workspaces(request: Request):
    try:
        catalog = await workspace_catalog()
        if request.method == "POST":
            body = await request.json()
            path = body.get("path")
            if not isinstance(path, str) or not path.strip():
                return JSONResponse({"error": "Enter a workspace directory"}, status_code=400)
            selected = validate_workspace(path, catalog.get("authorizedProjectRoots", []))
            return JSONResponse({"path": selected, "name": selected.rstrip("/").split("/")[-1]})
        return JSONResponse({"projects": catalog.get("savedProjects", []), "roots": catalog.get("authorizedProjectRoots", [])})
    except (ValueError, FileNotFoundError, NotADirectoryError) as exc:
        return JSONResponse({"error": str(exc)}, status_code=400)
    except Exception:
        return JSONResponse({"error": "Local System workspace service is unavailable"}, status_code=503)


app = Starlette(routes=[Route("/workspaces", workspaces, methods=["GET", "POST"])])
