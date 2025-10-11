import asyncio
import inspect
from functools import partial

from modules.app_logger import app_logger

async def _call_with_delay(callback, delay):
    is_async = inspect.iscoroutinefunction(callback)
    await asyncio.sleep(delay)
    if is_async:
        await callback()
    else:
        callback()


def call_with_delay(callback, delay=1):
    asyncio.create_task(_call_with_delay(callback, delay))


def _as_coro(func_or_coro, *args, **kwargs):
    """
    Normalize a callable/coroutine into a coroutine object.
    - If `func_or_coro` is already a coroutine object, return it.
    - If it's an async function, call it and return the coroutine.
    - If it's a sync function, run it in the default executor.
    """
    if inspect.iscoroutine(func_or_coro):
        return func_or_coro
    if inspect.iscoroutinefunction(func_or_coro):
        return func_or_coro(*args, **kwargs)

    async def _runner_sync():
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, lambda: func_or_coro(*args, **kwargs))

    return _runner_sync()


def run_after(
    a_func,
    a_args=(),
    a_kwargs=None,
    *,
    b_func=None,
    b_args=(),
    b_kwargs=None,
    loop=None,
    thread_safe=False,
    log_exceptions=True,
):
    """
    Fire-and-forget: run A, then (iff A succeeds) run B.
    Both A and B can be async or sync. A/B each accept independent args/kwargs.

    Parameters
    ----------
    a_func : Callable | Coroutine
        Function or coroutine for step A.
    a_args : tuple
        Positional args for A.
    a_kwargs : dict | None
        Keyword args for A.
    b_func : Callable | Coroutine | None
        Function or coroutine to run after A succeeds. If None, just run A.
    b_args : tuple
        Positional args for B.
    b_kwargs : dict | None
        Keyword args for B.
    loop : asyncio.AbstractEventLoop | None
        Event loop to use. Defaults to the current running loop.
    thread_safe : bool
        Use call_soon_threadsafe for scheduling B when B is sync.
    log_exceptions : bool
        If True, log exceptions from A instead of raising.

    Returns
    -------
    asyncio.Task
        The Task executing A.
    """
    if a_kwargs is None:
        a_kwargs = {}
    if b_kwargs is None:
        b_kwargs = {}

    if loop is None:
        loop = asyncio.get_running_loop()

    task = asyncio.create_task(_as_coro(a_func, *a_args, **a_kwargs))

    def _after(t: asyncio.Task):
        try:
            _ = t.result()
        except Exception:
            if log_exceptions:
                app_logger.error("run_after: A failed")
            return

        if b_func is None:
            return

        # Schedule B according to its type
        if inspect.iscoroutinefunction(b_func):
            asyncio.create_task(b_func(*b_args, **b_kwargs))
        else:
            cb = partial(b_func, *b_args, **b_kwargs)
            if thread_safe:
                loop.call_soon_threadsafe(cb)
            else:
                loop.call_soon(cb)

    task.add_done_callback(_after)
    return task
