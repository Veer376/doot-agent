import redis.asyncio as redis

redis_client = redis.Redis(
    host='redis-10032.c10.us-east-1-4.ec2.redns.redis-cloud.com',
    port=10032,
    decode_responses=True,
    username="default",
    password="REMOVED_CREDENTIAL",
)

async def test():
    pong = await redis_client.ping()
    print(f"Ping response: {pong}")
    
if __name__ == "__main__":
    import asyncio
    asyncio.run(test())