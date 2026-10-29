from types import SimpleNamespace

import pytest
from mcp.types import Tool
from doot_local.local_system import bridge_tool, effective_arguments
from doot_local.permissions import operation


def runtime(path):
    return SimpleNamespace(context={"workspace": str(path)})


def test_mcp_tool_schema_preserved():
    item = bridge_tool(Tool(name="execute_command", description="Run", inputSchema={"type": "object", "properties": {"command": {"type": "string"}}, "required": ["command"]}))
    assert item.name == "execute_command"
    assert "command" in item.args
    assert "runtime" not in item.args
    assert "runtime" in item._injected_args_keys


def test_explicit_selected_workspace(monkeypatch, tmp_path):
    monkeypatch.setenv("DOOT_WORKSPACE_ROOT", str(tmp_path))
    assert effective_arguments("execute_command", {"command": "pwd"}, runtime(tmp_path))["cwd"] == str(tmp_path)
    assert effective_arguments("apply_patch", {"input": "patch"}, runtime(tmp_path))["cwd"] == str(tmp_path)


@pytest.mark.parametrize("tool", ["execute_command", "apply_patch"])
def test_workspace_escape_rejected(monkeypatch, tmp_path, tool):
    monkeypatch.setenv("DOOT_WORKSPACE_ROOT", str(tmp_path))
    with pytest.raises(ValueError, match="outside"):
        effective_arguments(tool, {"cwd": ".."}, runtime(tmp_path))


def test_workspace_open_cannot_desynchronize_doot(monkeypatch, tmp_path):
    monkeypatch.setenv("DOOT_WORKSPACE_ROOT", str(tmp_path))
    (tmp_path / "nested").mkdir()
    with pytest.raises(ValueError, match="Select a different workspace"):
        effective_arguments("workspace", {"action": "open", "path": "nested"}, runtime(tmp_path))


def test_grants_match_mcp_command_and_patch(tmp_path):
    assert operation("execute_command", {"command": "pwd"}, str(tmp_path)) != operation("execute_command", {"command": "ls"}, str(tmp_path))
    assert operation("apply_patch", {"input": "first"}, str(tmp_path)) != operation("apply_patch", {"input": "second"}, str(tmp_path))


def test_patch_paths_cannot_escape_selected_workspace(monkeypatch, tmp_path):
    monkeypatch.setenv("DOOT_WORKSPACE_ROOT", str(tmp_path))
    with pytest.raises(ValueError, match="outside"):
        effective_arguments("apply_patch", {"input": "*** Begin Patch\n*** Add File: ../escape.txt\n+bad\n*** End Patch"}, runtime(tmp_path))


def test_images_reach_model_as_multimodal_blocks():
    from mcp.types import CallToolResult, ImageContent, TextContent
    from doot_local.local_system import result_message
    result = CallToolResult(content=[TextContent(type="text", text="First image"), ImageContent(type="image", data="aGVsbG8=", mimeType="image/png"), TextContent(type="text", text="Second image"), ImageContent(type="image", data="d29ybGQ=", mimeType="image/jpeg")])
    message = result_message("view_image", result, "image-call")
    assert message.content[1]["image_url"]["url"] == "data:image/png;base64,aGVsbG8="
    assert message.content[2]["text"] == "Second image"
    assert message.content[3]["image_url"]["url"] == "data:image/jpeg;base64,d29ybGQ="
    assert message.status == "success"


def test_image_paths_are_scoped(monkeypatch, tmp_path):
    monkeypatch.setenv("DOOT_WORKSPACE_ROOT", str(tmp_path))
    assert effective_arguments("view_image", {"paths": ["photo.png"]}, runtime(tmp_path))["paths"] == [str(tmp_path / "photo.png")]
    with pytest.raises(ValueError, match="outside"):
        effective_arguments("view_image", {"paths": ["../photo.png"]}, runtime(tmp_path))


def test_view_image_requires_no_approval(tmp_path):
    from doot_local.permissions import requires_review
    request = SimpleNamespace(tool_call={"name":"view_image", "args":{"paths":["photo.png"]}}, runtime=SimpleNamespace(context={"permission_mode":"ask"}))
    assert not requires_review(request)
