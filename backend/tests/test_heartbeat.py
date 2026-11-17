"""The worker's dead man's switch: it pings while the loop turns, goes silent when the loop is
stuck, comes back when it moves again, and a failed ping never stops it nor prints the URL."""

import asyncio
import logging
from collections.abc import Callable

import httpx
import pytest

from app.services.observability.heartbeat import LoopProgress, run_heartbeat

URL = "https://hc-ping.example/0b6f1c2e-secret-check-id"


def _client(answer: Callable[[httpx.Request], httpx.Response], seen: list[str]) -> httpx.AsyncClient:
    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(str(request.url))
        return answer(request)

    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


async def _keep_moving(progress: LoopProgress, stopping: asyncio.Event) -> None:
    while not stopping.is_set():
        progress.mark()
        await asyncio.sleep(0.002)


async def _run_for(seconds: float, client: httpx.AsyncClient, progress: LoopProgress, stuck_after: float) -> None:
    stopping = asyncio.Event()
    beat = asyncio.create_task(run_heartbeat(client, URL, progress, stopping, every=0.01, stuck_after=stuck_after))
    await asyncio.sleep(seconds)
    stopping.set()
    await asyncio.wait_for(beat, timeout=1)


async def test_it_pings_while_the_loop_moves() -> None:
    seen: list[str] = []
    progress, stopping = LoopProgress(), asyncio.Event()
    mover = asyncio.create_task(_keep_moving(progress, stopping))

    await _run_for(0.1, _client(lambda _: httpx.Response(200), seen), progress, stuck_after=1)
    stopping.set()
    await mover

    assert len(seen) >= 3 and set(seen) == {URL}


async def test_a_stuck_loop_goes_silent_and_says_so_once(caplog: pytest.LogCaptureFixture) -> None:
    seen: list[str] = []
    progress = LoopProgress()
    await asyncio.sleep(0.02)  # the loop last moved before the heartbeat's threshold

    with caplog.at_level(logging.INFO, logger="app.services.observability.heartbeat"):
        await _run_for(0.1, _client(lambda _: httpx.Response(200), seen), progress, stuck_after=0.01)

    assert seen == []  # the silence is what makes the monitoring service alert
    assert [r.levelno for r in caplog.records] == [logging.ERROR]


async def test_it_resumes_when_the_loop_moves_again(caplog: pytest.LogCaptureFixture) -> None:
    seen: list[str] = []
    progress, stopping = LoopProgress(), asyncio.Event()
    await asyncio.sleep(0.06)
    beat = asyncio.create_task(
        run_heartbeat(_client(lambda _: httpx.Response(200), seen), URL, progress, stopping, every=0.01, stuck_after=0.05)
    )

    with caplog.at_level(logging.INFO, logger="app.services.observability.heartbeat"):
        await asyncio.sleep(0.05)
        assert seen == []
        mover = asyncio.create_task(_keep_moving(progress, stopping))
        await asyncio.sleep(0.1)
        stopping.set()
        await asyncio.wait_for(asyncio.gather(beat, mover), timeout=1)

    assert seen, "the heartbeat should come back once the loop moves"
    assert "heartbeat resumed" in caplog.text


@pytest.mark.parametrize(
    ("answer", "logged"),
    [
        (lambda _: httpx.Response(503), "HTTP 503"),
        (lambda request: (_ for _ in ()).throw(httpx.ConnectError("refused", request=request)), "ConnectError"),
    ],
)
async def test_a_failed_ping_is_logged_without_the_url_and_does_not_stop_it(
    answer: Callable[[httpx.Request], httpx.Response], logged: str, caplog: pytest.LogCaptureFixture
) -> None:
    seen: list[str] = []
    progress, stopping = LoopProgress(), asyncio.Event()
    mover = asyncio.create_task(_keep_moving(progress, stopping))

    with caplog.at_level(logging.WARNING, logger="app.services.observability.heartbeat"):
        await _run_for(0.1, _client(answer, seen), progress, stuck_after=1)
    stopping.set()
    await mover

    assert len(seen) >= 3  # it keeps trying on every beat
    assert logged in caplog.text
    assert "secret-check-id" not in caplog.text
