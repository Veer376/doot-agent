from __future__ import annotations

from pathlib import Path

from langchain_core.tools import tool
from langchain.tools import ToolRuntime
from .workspaces import selected_workspace

from .config import load_settings


MAX_READ_BYTES = 1_000_000
MAX_LIST_ENTRIES = 200
MAX_COMMAND_OUTPUT = 20_000


def _resolve_workspace_path(path: str, runtime: ToolRuntime | None = None) -> Path:
    root = selected_workspace(runtime.context if runtime else None)
    candidate = (root / path).resolve() if not Path(path).is_absolute() else Path(path).resolve()

    try:
        candidate.relative_to(root)
    except ValueError as exc:
        raise ValueError(f"Path is outside the configured workspace: {path}") from exc

    from .permissions import state_directory
    state = state_directory()
    if candidate == state or state in candidate.parents:
        scratch = state / "scratch"
        if candidate != scratch and scratch not in candidate.parents:
            raise ValueError("Agent tools cannot access permission or workspace configuration")
    return candidate


@tool
def runtime_status(runtime: ToolRuntime = None) -> str:
    """Return the local Doot runtime model and workspace configuration."""
    settings = load_settings()
    return (
        f"model={settings.model}; "
        f"proxy={settings.proxy_url}; "
        f"workspace={selected_workspace(runtime.context if runtime else None)}"
    )


@tool
def list_workspace(path: str = ".", runtime: ToolRuntime = None) -> str:
    """List files and directories inside the configured local workspace."""
    target = _resolve_workspace_path(path, runtime)
    if not target.exists():
        return f"Path does not exist: {path}"
    if not target.is_dir():
        return f"Path is not a directory: {path}"

    entries = sorted(target.iterdir(), key=lambda item: (not item.is_dir(), item.name.lower()))
    lines: list[str] = []
    for entry in entries[:MAX_LIST_ENTRIES]:
        kind = "dir" if entry.is_dir() else "file"
        lines.append(f"{kind}\t{entry.relative_to(selected_workspace(runtime.context if runtime else None))}")

    if len(entries) > MAX_LIST_ENTRIES:
        lines.append(f"... {len(entries) - MAX_LIST_ENTRIES} more entries")
    return "\n".join(lines) if lines else "(empty)"


@tool
def request_user_input(question: str, options: list[str] | None = None) -> str:
    """Ask the user a necessary question and wait for an answer in the composer."""
    raise RuntimeError("Resume this native interrupt with a respond decision")


TOOLS = [request_user_input]
