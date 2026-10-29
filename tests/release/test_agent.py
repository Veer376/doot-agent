from pathlib import Path
from langchain_core.language_models.fake_chat_models import GenericFakeChatModel
from langchain_core.messages import AIMessage
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.types import Command
from orbit_core.agents import showcase_agent as agent

class ScriptedModel(GenericFakeChatModel):
    def bind_tools(self, tools, **kwargs):
        return self

def prepare(monkeypatch, tmp_path):
    responses = [
        AIMessage(content='',tool_calls=[{'name':'inspect_tickets','args':{},'id':'read-1'}]),
        AIMessage(content='',tool_calls=[{'name':'save_report','args':{'markdown':'# Triage\n6 tickets; 3 billing, 2 onboarding, 1 access.'},'id':'save-1'}]),
        AIMessage(content='Finished reviewing the tool result.'),
    ]
    model=ScriptedModel(messages=iter(responses))
    monkeypatch.setattr(agent,'get_model_instance',lambda *a,**k:model)
    monkeypatch.setenv('DOOT_OUTPUT_DIR',str(tmp_path))
    return agent.graph({}).compile(checkpointer=InMemorySaver()), {'configurable':{'thread_id':'release-test'}}

def test_fixture_counts():
    result=agent.inspect_tickets.invoke({})
    assert result['total']==6
    assert result['by_category']=={'billing':3,'onboarding':2,'access':1}
    assert result['by_priority']=={'high':3,'medium':2,'low':1}

async def test_approval_persists_and_resumes(monkeypatch,tmp_path):
    graph,config=prepare(monkeypatch,tmp_path)
    result=await graph.ainvoke({'messages':[('human','Inspect tickets and save a report')]},config)
    assert result['__interrupt__']
    assert not (tmp_path/'triage.md').exists()
    state=await graph.aget_state(config)
    interrupt=state.tasks[0].interrupts[0]
    assert interrupt.value['action_requests'][0]['name']=='save_report'
    await graph.ainvoke(Command(resume={interrupt.id:{'decisions':[{'type':'approve'}]}}),config)
    assert '6 tickets' in (tmp_path/'triage.md').read_text()
    assert not (await graph.aget_state(config)).next

async def test_rejection_does_not_write(monkeypatch,tmp_path):
    graph,config=prepare(monkeypatch,tmp_path)
    await graph.ainvoke({'messages':[('human','Inspect tickets and save a report')]},config)
    state=await graph.aget_state(config);i=state.tasks[0].interrupts[0]
    result=await graph.ainvoke(Command(resume={i.id:{'decisions':[{'type':'reject'}]}}),config)
    assert not (tmp_path/'triage.md').exists()
    assert any('declined' in str(m.content) for m in result['messages'])
