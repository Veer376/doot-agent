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


def test_graph_executes_local_tool():
    from doot_local.agent import graph

    result = graph.invoke(
        {
            "messages": [
                HumanMessage(
                    content=(
                        "You must call runtime_status. Then reply with only the model "
                        "value returned by that tool."
                    )
                )
            ]
        }
    )

    assert "gemini-3.8-flash-low" in result["messages"][-1].text


def test_graph_executes_local_command_tool():
    from doot_local.agent import graph

    result = graph.invoke(
        {
            "messages": [
                HumanMessage(
                    content=(
                        "You must call run_local_command with the command "
                        "printf AGENT_COMMAND_OK. Then reply with only the stdout."
                    )
                )
            ]
        }
    )

    assert "AGENT_COMMAND_OK" in result["messages"][-1].text
