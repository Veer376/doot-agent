from pathlib import Path
from types import SimpleNamespace

import pytest
from langchain_core.messages import AIMessage, ToolMessage
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.outputs import ChatResult, ChatGeneration
from langchain_core.tools import tool
from langchain.agents import create_agent
from langgraph.graph import StateGraph, MessagesState, START, END
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.prebuilt import ToolNode
from langgraph.runtime import Runtime
from langgraph.types import Command

from doot_local.permissions import PermissionMiddleware, permission_settings, requires_review, revoke_grant, set_default_mode
from doot_local.tools import TOOLS, _resolve_workspace_path
from doot_local.workspaces import register_workspace, prepare_workspace


@pytest.fixture(autouse=True)
def isolated(monkeypatch, tmp_path):
    monkeypatch.setenv("DOOT_WORKSPACE_ROOT", str(tmp_path / "workspace"))
    monkeypatch.setenv("DOOT_STATE_DIR", str(tmp_path / "policy"))
    (tmp_path / "workspace").mkdir()


def request(tmp_path, name="execute_command", args=None, mode="ask", thread="one", workspace=None):
    return SimpleNamespace(tool_call={"name":name,"args":args or {"command":"printf OK"}}, runtime=SimpleNamespace(context={"workspace":str(workspace or tmp_path / "workspace"),"permission_mode":mode}, execution_info=SimpleNamespace(thread_id=thread), config={}))


class FixtureModel(BaseChatModel):
    @property
    def _llm_type(self): return "approval-test-model"
    def bind_tools(self, tools, **kwargs): return self
    def _generate(self, messages, stop=None, run_manager=None, **kwargs):
        message = AIMessage(content="Done") if isinstance(messages[-1], ToolMessage) else messages[-1].model_copy(deep=True)
        return ChatResult(generations=[ChatGeneration(message=message)])


@tool("execute_command")
def fixture_command(command: str, cwd: str = ".") -> str:
    """A test-only no-op command; the real async command is tested separately."""
    return "Fixture command completed"


@tool("apply_patch")
def fixture_patch(patch: str) -> str:
    """A test-only minimal add-file operation for permission checks."""
    lines = patch.splitlines()
    path = _resolve_workspace_path(lines[1].removeprefix("*** Add File: "))
    path.write_text("\n".join(line[1:] for line in lines[2:-1]) + "\n")
    return "Applied patch"


def graph():
    tools = [fixture_command, fixture_patch, *TOOLS]
    return create_agent(FixtureModel(), tools, middleware=[PermissionMiddleware([t.name for t in tools])], context_schema=dict, checkpointer=InMemorySaver())


def input_call(name="apply_patch", args=None, call_id="test-call"):
    return {"messages":[AIMessage(content="", tool_calls=[{"name":name,"args":args or {"patch":"*** Begin Patch\n*** Add File: hello.txt\n+Hello\n*** End Patch"},"id":call_id}])]}


def context(tmp_path, mode="ask"):
    return {"workspace":str(tmp_path / "workspace"),"permission_mode":mode}


def test_native_interrupt_then_once_executes_only_after_approval(tmp_path):
    agent = graph(); config={"configurable":{"thread_id":"one"}}
    pause = agent.invoke(input_call(),config,context=context(tmp_path))
    assert pause["__interrupt__"][0].value["action_requests"][0]["name"] == "apply_patch"
    assert not (tmp_path/"workspace/hello.txt").exists()
    agent.invoke(Command(resume={"decisions":[{"type":"approve","scope":"once"}]}),config,context=context(tmp_path))
    assert (tmp_path/"workspace/hello.txt").read_text()=="Hello\n"
    assert permission_settings()["grants"] == []
    assert requires_review(request(tmp_path,"apply_patch",{}))


def test_native_reject_never_executes_or_remembers(tmp_path):
    agent=graph();config={"configurable":{"thread_id":"one"}}
    agent.invoke(input_call(),config,context=context(tmp_path))
    result=agent.invoke(Command(resume={"decisions":[{"type":"reject","scope":"always","message":"No"}]}),config,context={**context(tmp_path), "approval_grants":[{"name":"apply_patch","args":{"patch":"*** Begin Patch\n*** Add File: hello.txt\n+Hello\n*** End Patch"},"scope":"always"}]} )
    assert not (tmp_path/"workspace/hello.txt").exists()
    assert any(isinstance(m, ToolMessage) and m.status=="error" for m in result["messages"])
    assert permission_settings()["grants"]==[]


@pytest.mark.parametrize("scope",["conversation","always"])
def test_remembered_grants_isolate_workspace_thread_and_command(tmp_path,scope):
    agent=graph();config={"configurable":{"thread_id":"one"}}
    agent.invoke(input_call("execute_command",{"command":"printf OK"}),config,context=context(tmp_path))
    agent.invoke(Command(resume={"decisions":[{"type":"approve","scope":scope}]}),config,context={**context(tmp_path), "approval_grants":[{"name":"execute_command","args":{"command":"printf OK"},"scope":scope}]} )
    assert not requires_review(request(tmp_path))
    assert requires_review(request(tmp_path,args={"command":"printf DIFFERENT"}))
    assert requires_review(request(tmp_path,workspace=tmp_path/"other"))
    assert requires_review(request(tmp_path,thread="two")) == (scope == "conversation")
    grant=permission_settings()["grants"][0]
    revoke_grant(grant["workspace"],grant["scope"],grant["operation"])
    assert requires_review(request(tmp_path))


def test_mode_semantics_fail_closed(tmp_path):
    assert not requires_review(request(tmp_path,"list_workspace",{"path":"x"}))
    assert requires_review(request(tmp_path,"apply_patch",{},"ask"))
    assert not requires_review(request(tmp_path,"apply_patch",{},"auto"))
    assert requires_review(request(tmp_path,mode="auto"))
    assert not requires_review(request(tmp_path,mode="full"))
    assert requires_review(request(tmp_path,"future_tool",{},"auto"))
    with pytest.raises(ValueError): requires_review(request(tmp_path,mode="invalid"))
    set_default_mode("auto")
    assert permission_settings()["default_mode"]=="auto"
    with pytest.raises(ValueError): set_default_mode("unsafe")


def test_invalid_batch_cannot_persist_earlier_grant(tmp_path):
    agent=graph();config={"configurable":{"thread_id":"one"}}
    calls=input_call();calls["messages"][0].tool_calls.append({"name":"apply_patch","args":{"patch":"*** Begin Patch\n*** Add File: two.txt\n+Two\n*** End Patch"},"id":"two"})
    agent.invoke(calls,config,context=context(tmp_path))
    with pytest.raises(ValueError):
        agent.invoke(Command(resume={"decisions":[{"type":"approve","scope":"always"},{"type":"invalid"}]}),config,context={**context(tmp_path), "approval_grants":[{"name":"apply_patch","args":{"patch":"*** Begin Patch\n*** Add File: hello.txt\n+Hello\n*** End Patch"},"scope":"always"}]} )
    assert not (tmp_path/"workspace/hello.txt").exists()
    assert permission_settings()["grants"]==[]


def test_native_ask_user_respond_skips_tool_execution(tmp_path):
    agent=graph();config={"configurable":{"thread_id":"one"}}
    pause=agent.invoke(input_call("request_user_input",{"question":"Which file?","options":["a","b"]}),config,context=context(tmp_path,"full"))
    assert pause["__interrupt__"][0].value["review_configs"][0]["allowed_decisions"]==["respond"]
    result=agent.invoke(Command(resume={"decisions":[{"type":"respond","message":"a"}]}),config,context=context(tmp_path,"full"))
    assert any(isinstance(m, ToolMessage) and m.content=="a" for m in result["messages"])


def test_tool_runtime_workspace_and_protected_policy(tmp_path):
    runtime=SimpleNamespace(context=context(tmp_path))
    assert _resolve_workspace_path("x",runtime)==tmp_path/"workspace/x"
    with pytest.raises(ValueError): _resolve_workspace_path("../escape",runtime)
    (tmp_path/"workspace/link").symlink_to(tmp_path/"policy",target_is_directory=True)
    with pytest.raises(ValueError): _resolve_workspace_path("link/permissions.sqlite3",runtime)
    broad=SimpleNamespace(context={"workspace":str(tmp_path)})
    with pytest.raises(ValueError,match="configuration"): _resolve_workspace_path("policy/permissions.sqlite3",broad)


@pytest.mark.asyncio
async def test_registration_is_persistent_and_validation_requires_registration(tmp_path):
    extra=tmp_path/"new-project";extra.mkdir()
    with pytest.raises(ValueError): await prepare_workspace("one",str(extra))
    await register_workspace(str(extra))
    assert await prepare_workspace("one",str(extra))==str(extra)


def test_resume_cannot_change_bound_workspace_or_permission(tmp_path):
    for change in ({"workspace":str(tmp_path/"other")},{"permission_mode":"full"}):
        agent=graph(); config={"configurable":{"thread_id":"bound"}}
        values=input_call()
        values.update(execution_workspace=str(tmp_path/"workspace"),execution_permission_mode="ask")
        agent.invoke(values,config,context=context(tmp_path))
        with pytest.raises(ValueError,match="Cannot change"):
            agent.invoke(Command(resume={"decisions":[{"type":"approve"}]}),config,context={**context(tmp_path),**change})
        assert not (tmp_path/"workspace/hello.txt").exists()


def test_forged_grant_for_unapproved_action_fails_closed(tmp_path):
    agent=graph(); config={"configurable":{"thread_id":"forged"}}
    agent.invoke(input_call(),config,context=context(tmp_path))
    with pytest.raises(ValueError,match="does not match"):
        agent.invoke(Command(resume={"decisions":[{"type":"approve"}]}),config,context={**context(tmp_path),"approval_grants":[{"name":"execute_command","args":{"command":"evil"},"scope":"always"}]})
    assert permission_settings()["grants"]==[]
    assert not (tmp_path/"workspace/hello.txt").exists()
