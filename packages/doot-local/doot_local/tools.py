from __future__ import annotations

import asyncio
import os
import signal
from pathlib import Path

from langchain_core.tools import tool

from .config import load_settings


MAX_READ_BYTES = 1_000_000
MAX_LIST_ENTRIES = 200
MAX_COMMAND_OUTPUT = 20_000


def _resolve_workspace_path(path: str) -> Path:
    root = load_settings().workspace_root
    candidate = (root / path).resolve() if not Path(path).is_absolute() else Path(path).resolve()

    try:
        candidate.relative_to(root)
    except ValueError as exc:
        raise ValueError(f"Path is outside the configured workspace: {path}") from exc

    return candidate


@tool
def runtime_status() -> str:
    """Return the local Doot runtime model and workspace configuration."""
    settings = load_settings()
    return (
        f"model={settings.model}; "
        f"proxy={settings.proxy_url}; "
        f"workspace={settings.workspace_root}"
    )


@tool
def list_workspace(path: str = ".") -> str:
    """List files and directories inside the configured local workspace."""
    target = _resolve_workspace_path(path)
    if not target.exists():
        return f"Path does not exist: {path}"
    if not target.is_dir():
        return f"Path is not a directory: {path}"

    entries = sorted(target.iterdir(), key=lambda item: (not item.is_dir(), item.name.lower()))
    lines: list[str] = []
    for entry in entries[:MAX_LIST_ENTRIES]:
        kind = "dir" if entry.is_dir() else "file"
        lines.append(f"{kind}\t{entry.relative_to(load_settings().workspace_root)}")

    if len(entries) > MAX_LIST_ENTRIES:
        lines.append(f"... {len(entries) - MAX_LIST_ENTRIES} more entries")
    return "\n".join(lines) if lines else "(empty)"


@tool
def read_workspace_file(path: str, start_line: int = 1, end_line: int = 200) -> str:
    """Read a bounded line range from a UTF-8 text file in the configured workspace."""
    if start_line < 1:
        raise ValueError("start_line must be >= 1")
    if end_line < start_line:
        raise ValueError("end_line must be >= start_line")
    if end_line - start_line > 500:
        raise ValueError("At most 500 lines may be read at once")

    target = _resolve_workspace_path(path)
    if not target.exists():
        return f"File does not exist: {path}"
    if not target.is_file():
        return f"Path is not a file: {path}"
    if target.stat().st_size > MAX_READ_BYTES:
        raise ValueError(f"File is larger than {MAX_READ_BYTES} bytes")

    text = target.read_text(encoding="utf-8")
    lines = text.splitlines()
    selected = lines[start_line - 1 : end_line]
    return "\n".join(
        f"{line_number}: {line}"
        for line_number, line in enumerate(selected, start=start_line)
    )


@tool
def write_workspace_file(path: str, content: str) -> str:
    """Write a UTF-8 text file inside the configured workspace, creating parents."""
    target = _resolve_workspace_path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")
    return f"Wrote {len(content.encode('utf-8'))} bytes to {target.relative_to(load_settings().workspace_root)}"


@tool
def replace_workspace_text(path: str, old_text: str, new_text: str) -> str:
    """Replace exactly one occurrence of text in a UTF-8 workspace file."""
    if not old_text:
        raise ValueError("old_text must not be empty")

    target = _resolve_workspace_path(path)
    if not target.is_file():
        raise ValueError(f"File does not exist: {path}")
    if target.stat().st_size > MAX_READ_BYTES:
        raise ValueError(f"File is larger than {MAX_READ_BYTES} bytes")

    text = target.read_text(encoding="utf-8")
    count = text.count(old_text)
    if count != 1:
        raise ValueError(f"Expected exactly one match for old_text, found {count}")

    target.write_text(text.replace(old_text, new_text, 1), encoding="utf-8")
    return f"Updated {target.relative_to(load_settings().workspace_root)}"


@tool
async def run_local_command(command: str, cwd: str = ".", timeout_seconds: int = 120) -> str:
    """Run a local shell command from a workspace directory and return exit/output.

    This tool is intentionally powerful and is not sandboxed. The LangGraph API
    must remain localhost-only until a separate authentication boundary exists.
    """
    if timeout_seconds < 1 or timeout_seconds > 600:
        raise ValueError("timeout_seconds must be between 1 and 600")

    working_directory = _resolve_workspace_path(cwd)
    if not working_directory.is_dir():
        raise ValueError(f"cwd is not a directory: {cwd}")

    process = await asyncio.create_subprocess_shell(
        command,
        cwd=working_directory,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        start_new_session=os.name == "posix",
    )
    assert process.stdout is not None
    assert process.stderr is not None
    stdout_task = asyncio.create_task(process.stdout.read())
    stderr_task = asyncio.create_task(process.stderr.read())

    async def terminate_process_tree() -> None:
        if process.returncode is not None:
            return

        try:
            if os.name == "posix":
                os.killpg(process.pid, signal.SIGTERM)
            else:
                process.terminate()
        except ProcessLookupError:
            return

        try:
            await asyncio.wait_for(process.wait(), timeout=2)
            return
        except TimeoutError:
            pass

        try:
            if os.name == "posix":
                os.killpg(process.pid, signal.SIGKILL)
            else:
                process.kill()
        except ProcessLookupError:
            return
        await process.wait()

    try:
        try:
            await asyncio.wait_for(process.wait(), timeout=timeout_seconds)
        except TimeoutError:
            await terminate_process_tree()
            stdout_bytes, stderr_bytes = await asyncio.gather(stdout_task, stderr_task)
            stdout = stdout_bytes.decode("utf-8", errors="replace")[-MAX_COMMAND_OUTPUT:]
            stderr = stderr_bytes.decode("utf-8", errors="replace")[-MAX_COMMAND_OUTPUT:]
            return (
                f"Timed out after {timeout_seconds}s\n"
                f"stdout:\n{stdout}\n"
                f"stderr:\n{stderr}"
            )
    except asyncio.CancelledError:
        await terminate_process_tree()
        await asyncio.gather(stdout_task, stderr_task, return_exceptions=True)
        raise

    stdout_bytes, stderr_bytes = await asyncio.gather(stdout_task, stderr_task)
    stdout = stdout_bytes.decode("utf-8", errors="replace")[-MAX_COMMAND_OUTPUT:]
    stderr = stderr_bytes.decode("utf-8", errors="replace")[-MAX_COMMAND_OUTPUT:]
    return (
        f"exit_code={process.returncode}\n"
        f"stdout:\n{stdout}\n"
        f"stderr:\n{stderr}"
    )


TOOLS = [
    runtime_status,
    list_workspace,
    read_workspace_file,
    write_workspace_file,
    replace_workspace_text,
    run_local_command,
]
