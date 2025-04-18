from functools import wraps
from fastapi.concurrency import run_in_threadpool


def async_threadpool(func):
    @wraps(func)
    async def wrapper(*args, **kwargs):
        return await run_in_threadpool(func, *args, **kwargs)

    return wrapper
