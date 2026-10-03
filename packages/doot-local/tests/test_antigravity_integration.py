import os

import pytest
from langchain_core.messages import HumanMessage


pytestmark = pytest.mark.skipif(
    os.environ.get("DOOT_RUN_INTEGRATION_TESTS") != "1",
    reason="set DOOT_RUN_INTEGRATION_TESTS=1 to run live Antigravity tests",
)


def test_graph_uses_antigravity_proxy():
    from doot_local.agent import graph

    result = graph.invoke(
        {"messages": [HumanMessage(content="Reply exactly DOOT_GRAPH_OK.")]}
    )

    assert "DOOT_GRAPH_OK" in result["messages"][-1].text


@pytest.mark.asyncio
async def test_graph_executes_local_tool():
    from doot_local.agent import graph

    result = await graph.ainvoke(
        {
            "messages": [
                HumanMessage(
                    content=(
                        "You must call bridge_context. Then reply exactly DOOT_MCP_OK."
                    )
                )
            ]
        }
    )

    assert any(
        message.type == "tool" and getattr(message, "name", None) == "bridge_context"
        for message in result["messages"]
    )
    assert "DOOT_MCP_OK" in result["messages"][-1].text


@pytest.mark.asyncio
async def test_graph_executes_local_command_tool():
    from doot_local.agent import graph

    result = await graph.ainvoke(
        {
            "messages": [
                HumanMessage(
                    content=(
                        "First call bridge_context. Then call execute_command with "
                        "command printf AGENT_COMMAND_OK and cwd /tmp. "
                        "Reply with only AGENT_COMMAND_OK."
                    )
                )
            ]
        }
    )

    assert any(
        message.type == "tool" and getattr(message, "name", None) == "execute_command"
        for message in result["messages"]
    )
    assert "AGENT_COMMAND_OK" in result["messages"][-1].text
