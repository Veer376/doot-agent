"""Single-process run workers with replayable Redis events and PostgreSQL checkpoints."""
import asyncio
import json
from datetime import datetime, UTC
from langchain_core.load.dump import dumpd
from langchain_core.messages import message_chunk_to_message
from langgraph.types import Command
from orbit_core.clients import get_redis, get_supabase
from .graph import get_graph

TASKS: dict[str, asyncio.Task] = {}
def now(): return datetime.now(UTC).isoformat()
def encode(value):
    if hasattr(value, "model_dump"): return value.model_dump(mode="json")
    if hasattr(value, "_asdict"): return value._asdict()
    return str(value)

async def store_run(run):
    redis = await get_redis()
    await redis.set(f"run:{run['run_id']}", json.dumps(run, default=encode), ex=86400)
    await redis.sadd(f"thread:{run['thread_id']}:runs", run['run_id'])
    await redis.expire(f"thread:{run['thread_id']}:runs", 86400)

async def publish(run, event, data):
    redis = await get_redis()
    await redis.xadd(f"run:{run['run_id']}:events", {"event":event,"data":json.dumps(data,default=encode)}, maxlen=5000)
    await redis.expire(f"run:{run['run_id']}:events",86400)

async def process_run(run):
    db = await get_supabase()
    kwargs = run.pop("kwargs", {})
    try:
        run.update(status="running",updated_at=now());await store_run(run)
        await db.table("threads").update({"status":"busy"}).eq("thread_id",run['thread_id']).eq("user_id",run['user_id']).execute()
        graph = await get_graph(run['assistant_id'])
        config = {**kwargs.get("config", {}), "configurable": {"thread_id":run['thread_id']},"recursion_limit":30}
        command = kwargs.get("command")
        input_value = Command(**command) if command else kwargs.get("input")
        await publish(run,"metadata",{"run_id":run['run_id'],"thread_id":run['thread_id'],"attempt":1})
        async for mode,chunk in graph.astream(input_value,config=config,stream_mode=["messages","values"],context=kwargs.get("context")):
            if mode == "messages":
                msg,metadata=chunk
                await publish(run,"messages",[message_chunk_to_message(msg).model_dump(mode="json"),metadata])
            else:
                await publish(run,"values",chunk)
        snapshot=await graph.aget_state(config)
        interrupted=bool(snapshot.next)
        run.update(status="interrupted" if interrupted else "success",updated_at=now())
        await db.table("threads").update({"status":"interrupted" if interrupted else "idle",
            "values":json.loads(json.dumps(snapshot.values,default=encode))}).eq("thread_id",run['thread_id']).eq("user_id",run['user_id']).execute()
        if interrupted:
            await publish(run,"updates",{"__interrupt__":[encode(i) for t in snapshot.tasks for i in t.interrupts]})
    except asyncio.CancelledError:
        run.update(status="interrupted",updated_at=now())
        await db.table("threads").update({"status":"idle"}).eq("thread_id",run['thread_id']).eq("user_id",run['user_id']).execute()
    except Exception as exc:
        run.update(status="error",updated_at=now())
        await publish(run,"error",{"error":type(exc).__name__,"message":str(exc)})
        await db.table("threads").update({"status":"error"}).eq("thread_id",run['thread_id']).eq("user_id",run['user_id']).execute()
    finally:
        await store_run(run)
        await publish(run,"end",{})
        TASKS.pop(run['run_id'],None)
