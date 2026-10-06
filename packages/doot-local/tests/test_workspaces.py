from types import SimpleNamespace

import pytest
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
