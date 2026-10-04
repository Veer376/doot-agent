import os

import pytest
from langgraph_sdk import get_client


pytestmark = pytest.mark.skipif(
    os.environ.get("DOOT_RUN_API_TESTS") != "1",
    reason="set DOOT_RUN_API_TESTS=1 with a local LangGraph server running",
)

API_URL = os.environ.get("DOOT_LANGGRAPH_URL", "http://127.0.0.1:2024")


@pytest.mark.asyncio
async def test_native_double_text_interrupt_preserves_both_inputs():
    import asyncio

    client = get_client(url=API_URL)
    thread = await client.threads.create()
    thread_id = thread["thread_id"]
    first = await client.runs.create(thread_id, "doot", input={"messages": [{"id": "original", "role": "user", "content": "Write 2000 words about graph runtimes. Do not use tools."}]})
    await asyncio.sleep(1)
    second = await client.runs.create(thread_id, "doot", input={"messages": [{"id": "followup", "role": "user", "content": "Stop the explanation. Reply exactly DOUBLE_TEXT_OK."}]}, multitask_strategy="interrupt")
    await client.runs.join(thread_id, second["run_id"])
    assert (await client.runs.get(thread_id, first["run_id"]))["status"] == "interrupted"
    assert (await client.runs.get(thread_id, second["run_id"]))["status"] == "success"
    messages = (await client.threads.get_state(thread_id))["values"]["messages"]
    assert {"original", "followup"}.issubset({message["id"] for message in messages})
    assert "DOUBLE_TEXT_OK" in _message_text(messages[-1]["content"])


@pytest.mark.asyncio
async def test_edit_replaces_message_and_removes_later_conversation():
    client = get_client(url=API_URL)
    thread = await client.threads.create(metadata={"graph_id": "doot"})
    thread_id = thread["thread_id"]
    await client.threads.update_state(thread_id, values={"messages": [
        {"id": "edit-target", "role": "user", "content": "Original message"},
        {"id": "obsolete-answer", "role": "assistant", "content": "Obsolete answer"},
        {"id": "obsolete-followup", "role": "user", "content": "Obsolete followup"},
    ]})
    await client.threads.update_state(thread_id, values={"messages": [
        {"id": "edit-target", "role": "user", "content": "Reply exactly EDIT_REPLACED_OK. Do not use tools."},
        {"id": "obsolete-answer", "type": "remove", "content": ""},
        {"id": "obsolete-followup", "type": "remove", "content": ""},
    ]}, as_node="__start__")
    result = await client.runs.wait(thread_id, "doot", input=None)
    messages = result["messages"]
    assert len([message for message in messages if message["id"] == "edit-target"]) == 1
    assert not {"obsolete-answer", "obsolete-followup"}.intersection({message["id"] for message in messages})
    assert "EDIT_REPLACED_OK" in _message_text(messages[-1]["content"])


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
