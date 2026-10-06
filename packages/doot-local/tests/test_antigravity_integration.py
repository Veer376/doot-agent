import os

import pytest
from langchain_core.messages import HumanMessage


pytestmark = pytest.mark.skipif(
    os.environ.get("DOOT_RUN_INTEGRATION_TESTS") != "1",
    reason="set DOOT_RUN_INTEGRATION_TESTS=1 to run live Antigravity tests",
)


@pytest.mark.asyncio
async def test_graph_uses_antigravity_proxy():
    from doot_local.agent import build_graph

    graph = await build_graph()

    result = await graph.ainvoke(
        {"messages": [HumanMessage(content="Reply exactly DOOT_GRAPH_OK.")]},
        config={"configurable": {"thread_id": "integration-test"}}, context={"permission_mode": "full"},
    )

    assert "DOOT_GRAPH_OK" in result["messages"][-1].text


@pytest.mark.asyncio
async def test_graph_executes_local_tool():
    from doot_local.agent import build_graph

    graph = await build_graph()

    result = await graph.ainvoke(
        {
            "messages": [
                HumanMessage(
                    content=(
                        "You must call workspace with action list. Then reply exactly DOOT_NATIVE_OK."
                    )
                )
            ]
        },
        config={"configurable": {"thread_id": "integration-test"}}, context={"permission_mode": "full"},
    )

    assert any(
        message.type == "tool" and getattr(message, "name", None) == "workspace"
        for message in result["messages"]
    )
    assert "DOOT_NATIVE_OK" in result["messages"][-1].text


@pytest.mark.asyncio
async def test_graph_executes_local_command_tool():
    from doot_local.agent import build_graph

    graph = await build_graph()

    result = await graph.ainvoke(
        {
            "messages": [
                HumanMessage(
                    content=(
                        "First call workspace with action list. Then call execute_command with "
                        "command printf AGENT_COMMAND_OK. "
                        "Reply with only AGENT_COMMAND_OK."
                    )
                )
            ]
        },
        config={"configurable": {"thread_id": "integration-test"}}, context={"permission_mode": "full"},
    )

    assert any(
        message.type == "tool" and getattr(message, "name", None) == "execute_command"
        for message in result["messages"]
    )
    assert "AGENT_COMMAND_OK" in result["messages"][-1].text
