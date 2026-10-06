from __future__ import annotations

import asyncio
import hashlib
import json
from pathlib import Path
from .config import load_settings


def conversation_id(thread_id: str, workspace: str | None) -> str:
    normalized = str(Path(workspace).expanduser().resolve()) if workspace else "projectless"
    return f"doot:{thread_id}:{hashlib.sha256(normalized.encode()).hexdigest()[:16]}"


def validate_workspace(path: str, roots: list[str]) -> str:
    selected = Path(path).expanduser().resolve(strict=True)
    if not selected.is_dir():
        raise ValueError("Workspace must be a directory")
    for root in roots:
        authorized = Path(root).expanduser().resolve()
        if selected == authorized or authorized in selected.parents:
            return str(selected)
    raise ValueError("Workspace is outside the authorized project roots; select it in the workspace picker")


def catalog_file() -> Path:
    from .permissions import state_directory
    return state_directory() / "workspaces.json"


def _workspace_catalog() -> dict:
    default = str(load_settings().workspace_root)
    path = catalog_file()
    if path.exists():
        return json.loads(path.read_text())
    return {"savedProjects": [{"name": Path(default).name, "path": default}], "authorizedProjectRoots": [default]}


def _register_workspace(path: str) -> str:
    # User-only HTTP action; never exposed as an agent tool.
    import fcntl
    from .permissions import state_directory
    selected = Path(path).expanduser().resolve(strict=True)
    if not selected.is_dir():
        raise ValueError("Workspace must be a directory")
    with (state_directory() / "workspaces.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        catalog = _workspace_catalog()
        if str(selected) not in catalog["authorizedProjectRoots"]:
            catalog["authorizedProjectRoots"].append(str(selected))
            catalog["savedProjects"].append({"name": selected.name, "path": str(selected)})
        temporary = catalog_file().with_suffix(".tmp")
        temporary.write_text(json.dumps(catalog, indent=2))
        temporary.replace(catalog_file())
    return str(selected)


def selected_workspace(context: dict | None) -> Path:
    if context is None:
        return load_settings().workspace_root
    workspace = context.get("workspace")
    if workspace:
        return Path(workspace).expanduser().resolve()
    from .permissions import state_directory
    scratch = state_directory() / "scratch"
    scratch.mkdir(exist_ok=True)
    return scratch


def _prepare_workspace(thread_id: str, workspace: str | None) -> str | None:
    if not thread_id:
        raise ValueError("A LangGraph thread is required")
    if workspace:
        catalog = _workspace_catalog()
        return validate_workspace(workspace, catalog["authorizedProjectRoots"])
    selected_workspace({})
    return None


async def workspace_catalog() -> dict:
    return await asyncio.to_thread(_workspace_catalog)


async def register_workspace(path: str) -> str:
    return await asyncio.to_thread(_register_workspace, path)


async def prepare_workspace(thread_id: str, workspace: str | None) -> str | None:
    return await asyncio.to_thread(_prepare_workspace, thread_id, workspace)
