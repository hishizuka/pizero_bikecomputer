import asyncio
import inspect


async def _call_with_delay(callback, delay):
    is_async = inspect.iscoroutinefunction(callback)
    await asyncio.sleep(delay)
    if is_async:
        await callback()
    else:
        callback()


def call_with_delay(callback, delay=1):
    asyncio.create_task(_call_with_delay(callback, delay))
