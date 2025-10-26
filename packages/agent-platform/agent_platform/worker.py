import sys
import asyncio
import json
from langchain_core.messages import BaseMessage
import json
from orbit_core.clients import get_redis
import logging
from .schema import Run
from .utils import map_cmd
from .graph import get_graph

logger = logging.getLogger("worker")


async def process_run(run: Run):
    """Process a run and stream the results via Redis"""
    # FIXME: validate_run, and handle based on multitask_strategy.

    run_id = run["run_id"]
    assistant_id = run["assistant_id"]
    if not assistant_id:
        raise ValueError(f"Run {run_id} does not have an assistant_id")

    thread_id = run["thread_id"]
    metadata = run.get("metadata", {})
    multitask_strategy = run.get("multitask_strategy", "enqueue")
    kwargs = run.get("kwargs", {})

    # NOTE: Assumes assistant and graph IDs are identical — a deliberate simplification while assistant creation is not supported.
    # TODO: Task - implement assistant creation.
    graph = await get_graph(assistant_id)

    webhook = kwargs.get("webhook", None)
    stream_resumable = kwargs.get(
        "stream_resumable", False
    )  # TODO: Implement stream resumable handling
    feedback_keys = kwargs.get("feedback_keys", None)

    if metadata or feedback_keys or webhook:
        logger.warning(
            f"Run {run_id} has metadata or feedback_keys, but handling not implemented yet"
        )

    input = kwargs.get("input", None)
    if cmd := kwargs.get("command", None):
        input = map_cmd(cmd)

    config: dict = kwargs.get("config", {})
    configurable = config.pop("configurable", {})

    config = {
        **config,
        "configurable": {
            "thread_id": thread_id,
            **kwargs.get("checkpoint", {}),
            **configurable,
        },
        "recursion_limit": 5000,
        # "run_id": run_id
        # "callbacks": [] # NOTE: Callbacks has whole different story which needs to be envisioned.
    }

    redis_client = get_redis()

    try:
        run["status"] = "running"

        async for stream_mode, chunk in graph.astream(
            input=input,
            config=config,
            context=kwargs.get("context", {}),
            stream_mode=["messages", "values", "updates"],
            interrupt_after=kwargs.get("interrupt_after", None),
            interrupt_before=kwargs.get("interrupt_before", None),
            durability=kwargs.get("durability", "async"),
            # subgraphs=kwargs.get("subgraphs", True), # FIXME: add subgraph destructuring
        ):

            if stream_mode == "values":
                # Serialize messages if they exist
                data = {}

                if messages := chunk.get("messages", None):
                    dict_messages = [
                        (
                            msg.model_dump(exclude_none=True)
                            if isinstance(msg, BaseMessage)
                            else msg
                        )
                        for msg in messages
                    ]
                    data["messages"] = dict_messages

                # Include other state fields (browser_snapshot, etc.)
                for key, value in chunk.items():
                    if key != "messages":  # Already handled above
                        data[key] = value

                await redis_client.publish(
                    f"run:{run_id}:stream",
                    json.dumps(
                        {
                            "event": "values",
                            "data": data,
                            "run_id": run_id,
                            "thread_id": thread_id,
                        }
                    ),
                )

            if stream_mode == "messages":
                if isinstance(chunk, tuple):
                    chunk_list = []
                    for item in chunk:
                        if isinstance(item, BaseMessage):
                            # TODO: create a custom serialization method to handle empty fields.
                            chunk_list.append(item.model_dump(exclude_none=True))
                        else:
                            chunk_list.append(item)

                await redis_client.publish(
                    f"run:{run_id}:stream",
                    json.dumps(
                        {
                            "event": "messages",
                            "data": chunk_list,
                            "run_id": run_id,
                            "thread_id": thread_id,
                        }
                    ),
                )

        await redis_client.publish(
            f"run:{run_id}:stream",
            json.dumps(
                {
                    "event": "status",
                    "status": "completed",
                    "run_id": run_id,
                    "thread_id": thread_id,
                }
            ),
        )

    except Exception as e:
        import traceback

        traceback.print_exc()
        run["status"] = "error"
        await redis_client.publish(
            f"run:{run_id}:stream",
            json.dumps(
                {
                    "type": "status",
                    "status": "error",
                    "error": str(e),
                    "run_id": run_id,
                    "thread_id": thread_id,
                }
            ),
        )
        print(f"Error processing run {run_id}: {e}")


async def main():

    while True:
        print("Waiting for work...")
        redis_client = get_redis()
        result = await redis_client.blpop("run:queue", timeout=3)

        if result:
            run_id = result[1]
            print(f"Received run with ID: {run_id}")
            asyncio.create_task(process_run(run_id))


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("Shutting down...")
        sys.exit(0)
    except Exception as e:
        print(f"Error: {e}")
        sys.exit(1)
