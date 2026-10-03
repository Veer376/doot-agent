import os

import pytest
from langgraph_sdk import get_client


pytestmark = pytest.mark.skipif(
    os.environ.get("DOOT_RUN_API_TESTS") != "1",
    reason="set DOOT_RUN_API_TESTS=1 with a local LangGraph server running",
)

API_URL = os.environ.get("DOOT_LANGGRAPH_URL", "http://127.0.0.1:2024")


def _message_text(content) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "".join(
            block.get("text", "")
            for block in content
            if isinstance(block, dict) and block.get("type") == "text"
        )
    return str(content)


@pytest.mark.asyncio
async def test_assistant_is_discoverable():
    client = get_client(url=API_URL)
    assistants = await client.assistants.search(graph_id="doot")

    assert assistants
    assert any(assistant["graph_id"] == "doot" for assistant in assistants)


@pytest.mark.asyncio
async def test_thread_stream_and_persistence():
    client = get_client(url=API_URL)
    thread = await client.threads.create()
    thread_id = thread["thread_id"]

    first_events = []
    async for event in client.runs.stream(
        thread_id,
        "doot",
        input={"messages": [{"role": "user", "content": "Remember the marker ORBIT_731."}]},
        stream_mode="values",
    ):
        first_events.append(event)

    assert first_events

    second = await client.runs.wait(
        thread_id,
        "doot",
        input={
            "messages": [
                {
                    "role": "user",
                    "content": "What marker did I ask you to remember? Reply with only the marker.",
                }
            ]
        },
    )

    last_message = second["messages"][-1]
    assert "ORBIT_731" in last_message["content"]


@pytest.mark.asyncio
async def test_tool_call_is_visible_in_thread_state():
    client = get_client(url=API_URL)
    thread = await client.threads.create()
    thread_id = thread["thread_id"]

    await client.runs.wait(
        thread_id,
        "doot",
        input={
            "messages": [
                {
                    "role": "user",
                    "content": "You must call bridge_context. Then reply exactly API_MCP_OK.",
                }
            ]
        },
    )

    state = await client.threads.get_state(thread_id)
    messages = state["values"]["messages"]

    assert any(
        message.get("type") == "tool" and message.get("name") == "bridge_context"
        for message in messages
    )
    assert "API_MCP_OK" in _message_text(messages[-1]["content"])
