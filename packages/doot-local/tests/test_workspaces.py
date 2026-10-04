from types import SimpleNamespace

import pytest
from langchain_mcp_adapters.interceptors import MCPToolCallRequest

from doot_local.mcp_tools import workspace_interceptor
from doot_local.workspaces import conversation_id, validate_workspace


def test_workspace_validation_rejects_sibling_and_symlink_escape(tmp_path):
    root = tmp_path / "projects"
    project = root / "one"
    project.mkdir(parents=True)
    sibling = tmp_path / "projects-other"
    sibling.mkdir()
    escape = root / "escape"
    escape.symlink_to(sibling, target_is_directory=True)
    assert validate_workspace(str(project), [str(root)]) == str(project)
    for path in (sibling, escape):
        with pytest.raises(ValueError, match="authorized"):
            validate_workspace(str(path), [str(root)])


def test_conversations_are_isolated_by_thread_and_workspace(tmp_path):
    first = conversation_id("one", str(tmp_path))
    assert first == conversation_id("one", str(tmp_path / "."))
    assert first != conversation_id("two", str(tmp_path))
    assert first != conversation_id("one", None)
    assert first != conversation_id("one", str(tmp_path / "other"))


@pytest.mark.asyncio
async def test_tool_runtime_routes_workspace_and_preserves_auth(tmp_path):
    captured = []
    async def handler(request):
        captured.append(request)
        return "ok"
    runtime = SimpleNamespace(context={"workspace": str(tmp_path)}, execution_info=SimpleNamespace(thread_id="one"))
    request = MCPToolCallRequest(name="execute_command", args={"command": "pwd"}, server_name="local_system", headers={"Authorization": "test-token"}, runtime=runtime)
    assert await workspace_interceptor(request, handler) == "ok"
    assert captured[0].args["cwd"] == str(tmp_path)
    assert captured[0].headers == {"Authorization": "test-token", "x-conversation-id": conversation_id("one", str(tmp_path))}
    assert "cwd" not in request.args
    with pytest.raises(ValueError, match="outside"):
        await workspace_interceptor(request.override(args={"command": "pwd", "cwd": str(tmp_path.parent)}), handler)


@pytest.mark.asyncio
async def test_tools_require_thread_identity():
    request = MCPToolCallRequest(name="bridge_context", args={}, server_name="local_system")
    with pytest.raises(ValueError, match="thread"):
        await workspace_interceptor(request, None)
