import asyncio
import shlex

import pytest

from doot_local.tools import (
    list_workspace,
    read_workspace_file,
    replace_workspace_text,
    run_local_command,
    write_workspace_file,
)


def test_list_workspace_is_scoped(monkeypatch, tmp_path):
    (tmp_path / "alpha.txt").write_text("alpha\n", encoding="utf-8")
    monkeypatch.setenv("DOOT_WORKSPACE_ROOT", str(tmp_path))

    result = list_workspace.invoke({"path": "."})

    assert "alpha.txt" in result


def test_read_workspace_file(monkeypatch, tmp_path):
    (tmp_path / "sample.txt").write_text("one\ntwo\nthree\n", encoding="utf-8")
    monkeypatch.setenv("DOOT_WORKSPACE_ROOT", str(tmp_path))

    result = read_workspace_file.invoke(
        {"path": "sample.txt", "start_line": 2, "end_line": 3}
    )

    assert result == "2: two\n3: three"


def test_workspace_escape_is_rejected(monkeypatch, tmp_path):
    monkeypatch.setenv("DOOT_WORKSPACE_ROOT", str(tmp_path))

    with pytest.raises(ValueError, match="outside the configured workspace"):
        read_workspace_file.invoke({"path": "../outside.txt"})


def test_write_and_replace_workspace_file(monkeypatch, tmp_path):
    monkeypatch.setenv("DOOT_WORKSPACE_ROOT", str(tmp_path))

    write_workspace_file.invoke({"path": "nested/value.txt", "content": "alpha\n"})
    replace_workspace_text.invoke(
        {"path": "nested/value.txt", "old_text": "alpha", "new_text": "beta"}
    )

    assert (tmp_path / "nested/value.txt").read_text(encoding="utf-8") == "beta\n"


@pytest.mark.asyncio
async def test_run_local_command(monkeypatch, tmp_path):
    monkeypatch.setenv("DOOT_WORKSPACE_ROOT", str(tmp_path))

    result = await run_local_command.ainvoke(
        {"command": "printf 'COMMAND_OK'", "cwd": ".", "timeout_seconds": 5}
    )

    assert "exit_code=0" in result
    assert "COMMAND_OK" in result


@pytest.mark.asyncio
async def test_run_local_command_cancellation_kills_process_group(monkeypatch, tmp_path):
    monkeypatch.setenv("DOOT_WORKSPACE_ROOT", str(tmp_path))
    started = tmp_path / "started"
    done = tmp_path / "done"
    command = (
        f"touch {shlex.quote(str(started))}; "
        f"sleep 30; touch {shlex.quote(str(done))}"
    )

    task = asyncio.create_task(
        run_local_command.ainvoke(
            {"command": command, "cwd": ".", "timeout_seconds": 60}
        )
    )
    for _ in range(100):
        if started.exists():
            break
        await asyncio.sleep(0.05)

    assert started.exists()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task

    await asyncio.sleep(0.2)
    assert not done.exists()
