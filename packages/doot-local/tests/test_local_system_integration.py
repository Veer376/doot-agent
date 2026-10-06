import asyncio, json, os, uuid
from pathlib import Path
from langchain.agents import create_agent
from langchain_core.messages import AIMessage, ToolMessage
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.types import Command
from doot_local.local_system import load_tools
from doot_local.permissions import PermissionMiddleware
import pytest
from test_permissions import FixtureModel

pytestmark = [pytest.mark.asyncio, pytest.mark.skipif(os.getenv("DOOT_RUN_INTEGRATION_TESTS") != "1", reason="Opt-in live Local System MCP test")]

async def test_mcp_approval_patch_and_managed_task(monkeypatch, tmp_path):
    monkeypatch.setenv("DOOT_STATE_DIR", str(tmp_path / "policy"))
    root=Path(__file__).resolve().parents[3]
    (root / ".doot").mkdir(exist_ok=True)
    marker=root/'.doot'/f'mcp-smoke-{uuid.uuid4().hex}.txt'
    denied=marker.with_suffix('.denied')
    tools=await load_tools()
    graph=create_agent(FixtureModel(), tools, middleware=[PermissionMiddleware([t.name for t in tools])], context_schema=dict, checkpointer=InMemorySaver())
    context={'workspace':str(root),'permission_mode':'ask'}
    config={'configurable':{'thread_id':f'mcp-smoke-{uuid.uuid4().hex}'}}
    def call(name,args):return {'messages':[AIMessage(content='', tool_calls=[{'name':name,'args':args,'id':uuid.uuid4().hex}])]}
    try:
        result=await graph.ainvoke(call('execute_command',{'command':f'printf MCP_APPROVED > {marker}','waitMs':1000}),config,context=context)
        assert result['__interrupt__'] and not marker.exists()
        result=await graph.ainvoke(Command(resume={'decisions':[{'type':'approve'}]}),config,context=context)
        assert marker.read_text()=='MCP_APPROVED',result
        result=await graph.ainvoke(call('execute_command',{'command':f'printf BAD > {denied}'}),config,context=context)
        assert result['__interrupt__']
        await graph.ainvoke(Command(resume={'decisions':[{'type':'reject','message':'Denied. Stop.'}]}),config,context=context)
        assert not denied.exists()
        patch=f'*** Begin Patch\n*** Update File: {marker.relative_to(root)}\n@@\n-MCP_APPROVED\n+MCP_PATCHED\n*** End Patch'
        result=await graph.ainvoke(call('apply_patch',{'input':patch}),config,context={**context,'permission_mode':'auto'})
        assert marker.read_text().strip()=='MCP_PATCHED',result
        result=await graph.ainvoke(call('execute_command',{'command':'sleep 1; printf MANAGED_OK','waitMs':0}),config,context={**context,'permission_mode':'full'})
        message=next(m for m in reversed(result['messages']) if isinstance(m,ToolMessage))
        payload=json.loads(message.content)['structuredContent']
        print('managed task keys:',list(payload))
        taskid=payload.get('taskId') or payload.get('id')
        assert taskid, payload
        await asyncio.sleep(1.2)
        result=await graph.ainvoke(call('manage_task',{'action':'status','taskId':taskid}),config,context=context)
        assert 'MANAGED_OK' in str(result['messages'][-2].content)
        print('PASS: exact six tools; real MCP command paused, approved, rejected; patch applied; managed task resumed')
    finally:
        marker.unlink(missing_ok=True);denied.unlink(missing_ok=True)
