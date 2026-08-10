import httpx
import pytest

from app.services.agent.tools.retry import retry_async


async def test_retry_async_succeeds_first_try() -> None:
    calls = 0

    async def _fn() -> str:
        nonlocal calls
        calls += 1
        return "ok"

    result = await retry_async(_fn)
    assert result == "ok"
    assert calls == 1


async def test_retry_async_retries_on_transport_error_then_succeeds() -> None:
    calls = 0

    async def _fn() -> str:
        nonlocal calls
        calls += 1
        if calls < 3:
            raise httpx.ConnectError("boom")
        return "ok"

    result = await retry_async(_fn, base_delay=0.001)
    assert result == "ok"
    assert calls == 3


async def test_retry_async_gives_up_after_max_attempts() -> None:
    async def _fn() -> str:
        raise httpx.ConnectError("always fails")

    with pytest.raises(httpx.ConnectError):
        await retry_async(_fn, attempts=2, base_delay=0.001)


async def test_retry_async_does_not_retry_client_errors() -> None:
    calls = 0

    async def _fn() -> str:
        nonlocal calls
        calls += 1
        request = httpx.Request("GET", "http://example.com")
        response = httpx.Response(400, request=request)
        raise httpx.HTTPStatusError("bad request", request=request, response=response)

    with pytest.raises(httpx.HTTPStatusError):
        await retry_async(_fn, base_delay=0.001)
    assert calls == 1
