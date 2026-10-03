import os

import pytest
from langgraph_sdk import get_client


pytestmark = pytest.mark.skipif(
    os.environ.get("DOOT_RUN_API_TESTS") != "1",
    reason="set DOOT_RUN_API_TESTS=1 with a local LangGraph server running",
)

API_URL = os.environ.get("DOOT_LANGGRAPH_URL", "http://127.0.0.1:2024")


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
                    "content": (
                        "You must call runtime_status. Then tell me which model the tool reports."
                    ),
                }
            ]
        },
    )

    state = await client.threads.get_state(thread_id)
    messages = state["values"]["messages"]

    assert any(message.get("type") == "tool" for message in messages)
    assert "gemini-3.8-flash-low" in messages[-1]["content"]
