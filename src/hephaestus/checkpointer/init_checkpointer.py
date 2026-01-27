import asyncio
from hephaestus.settings import settings
from langgraph.checkpoint.redis.aio import AsyncRedisSaver

async def _setup_checkpointer():
    """Initialize the Redis checkpointer."""
    checkpointer = AsyncRedisSaver(redis_url=f'redis://{settings.REDIS_URL}')
    await checkpointer.asetup()
    return checkpointer

checkpointer = asyncio.run(_setup_checkpointer())

