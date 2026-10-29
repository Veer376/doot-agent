"""LangGraph SDK run subset used by the web release."""
import asyncio
import json
from uuid import uuid4
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.responses import StreamingResponse
from orbit_core.clients import get_redis, get_supabase
from ..utils import authenticate_user
from ..release_threads import owned
from ...worker import process_run, store_run, TASKS, now

runs_router=APIRouter()
async def load(run_id,thread_id,user_id):
    redis=await get_redis();raw=await redis.get(f"run:{run_id}")
    run=json.loads(raw) if raw else None
    if not run or run['thread_id']!=thread_id or run['user_id']!=user_id:
        raise HTTPException(404,"Run not found")
    return run

def stream(thread_id,run_id,user_id,cursor="0-0"):
    async def events():
        nonlocal cursor
        redis=await get_redis()
        while True:
            batches=await redis.xread({f"run:{run_id}:events":cursor},block=15000,count=100)
            if not batches:
                run=await load(run_id,thread_id,user_id)
                if run['status'] not in ('pending','running'):break
                yield ': keepalive\n\n';continue
            for _,entries in batches:
                for event_id,fields in entries:
                    cursor=event_id
                    event=fields['event']
                    yield f"id: {event_id}\nevent: {event}\ndata: {fields['data']}\n\n"
                    if event=='end':return
    return StreamingResponse(events(),media_type="text/event-stream",headers={"Cache-Control":"no-cache","X-Accel-Buffering":"no"})

@runs_router.post('/threads/{thread_id}/runs/stream')
async def create(thread_id: str,body: dict,request: Request,user_id=Depends(authenticate_user)):
    thread=await owned(thread_id,user_id)
    redis=await get_redis()
    lock=f"thread:{thread_id}:active"
    run_id=str(uuid4())
    if not await redis.set(lock,run_id,nx=True,ex=3600):
        old=await redis.get(lock)
        try:active=await load(old,thread_id,user_id)
        except HTTPException:active=None
        if active and active['status'] in ('pending','running'):raise HTTPException(409,"Thread already has an active run")
        await redis.delete(lock)
        if not await redis.set(lock,run_id,nx=True,ex=3600):raise HTTPException(409,"Thread busy")
    assistant=body.get('assistant_id') or thread.get('metadata',{}).get('assistant_id','chat_agent')
    if assistant!='chat_agent':
        await redis.delete(lock);raise HTTPException(404,'Assistant not supported by release profile')
    db=await get_supabase()
    await db.table('threads').update({'metadata':{**thread.get('metadata',{}),'assistant_id':assistant}}).eq('thread_id',thread_id).eq('user_id',user_id).execute()
    run={'run_id':run_id,'thread_id':thread_id,'assistant_id':assistant,'user_id':user_id,'status':'pending','created_at':now(),'updated_at':now()}
    await store_run(run)
    async def work():
        try:await process_run({**run,'kwargs':body})
        finally:
            if await redis.get(lock)==run_id:await redis.delete(lock)
    TASKS[run_id]=asyncio.create_task(work())
    return stream(thread_id,run_id,user_id)

@runs_router.get('/threads/{thread_id}/runs')
async def list_runs(thread_id: str,status: str|None=None,limit:int=10,user_id=Depends(authenticate_user)):
    await owned(thread_id,user_id);redis=await get_redis();results=[]
    for run_id in await redis.smembers(f'thread:{thread_id}:runs'):
        try:run=await load(run_id,thread_id,user_id)
        except HTTPException:continue
        if not status or run['status']==status:results.append(run)
    return sorted(results,key=lambda r:r['created_at'],reverse=True)[:min(limit,100)]

@runs_router.get('/threads/{thread_id}/runs/{run_id}')
async def get_run(thread_id:str,run_id:str,user_id=Depends(authenticate_user)):
    return await load(run_id,thread_id,user_id)

@runs_router.get('/threads/{thread_id}/runs/{run_id}/stream')
async def join(thread_id:str,run_id:str,request:Request,user_id=Depends(authenticate_user)):
    await load(run_id,thread_id,user_id)
    cursor=request.headers.get('last-event-id','0-0')
    if not __import__('re').fullmatch(r'\d+-\d+',cursor):raise HTTPException(400,'Invalid event cursor')
    return stream(thread_id,run_id,user_id,cursor)

@runs_router.post('/threads/{thread_id}/runs/{run_id}/cancel')
async def cancel(thread_id:str,run_id:str,user_id=Depends(authenticate_user)):
    run=await load(run_id,thread_id,user_id)
    if task:=TASKS.get(run_id):
        task.cancel();await asyncio.gather(task,return_exceptions=True)
    return Response(status_code=204)
