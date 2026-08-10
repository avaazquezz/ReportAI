import asyncio
from collections.abc import Awaitable, Callable
from typing import TypeVar

import httpx

T = TypeVar("T")


async def retry_async(fn: Callable[[], Awaitable[T]], attempts: int = 3, base_delay: float = 1.0) -> T:
    """Retry with exponential backoff on transient HTTP failures (5xx, 429, connection errors).

    Non-retryable HTTP errors (4xx other than 429) raise immediately — a
    malformed request won't succeed just because we tried it again.
    """
    last_exc: Exception | None = None
    for attempt in range(attempts):
        try:
            return await fn()
        except (httpx.TransportError, httpx.HTTPStatusError) as exc:
            last_exc = exc
            if isinstance(exc, httpx.HTTPStatusError):
                status = exc.response.status_code
                if status < 500 and status != 429:
                    raise
            if attempt < attempts - 1:
                await asyncio.sleep(base_delay * (2**attempt))
    assert last_exc is not None
    raise last_exc
