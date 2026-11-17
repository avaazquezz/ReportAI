"""The worker's dead man's switch. While its loop keeps turning, the worker requests
WORKER_HEARTBEAT_URL; the monitoring service that URL belongs to alerts when the requests stop.

The API's /health can't see the worker: the API answers "ok" while reports pile up behind a worker
that crashes on start, hangs, or has lost its way out to the internet. Silence is the signal, so
it also covers what no code here can report: the container gone, the server down."""

import asyncio
import logging
import time

import httpx

logger = logging.getLogger(__name__)


class LoopProgress:
    """When the worker's loop last went round. One round includes a whole job, so a long job is
    not a hang: only a loop that hasn't moved for longer than any job may take is stuck."""

    def __init__(self) -> None:
        self._at = time.monotonic()

    def mark(self) -> None:
        self._at = time.monotonic()

    def idle_for(self) -> float:
        return time.monotonic() - self._at


async def _ping(client: httpx.AsyncClient, url: str) -> None:
    try:
        response = await client.get(url, timeout=10)
        response.raise_for_status()
    except httpx.HTTPStatusError as exc:
        # Never the URL: whoever holds it can make a dead worker look alive.
        logger.warning("Worker heartbeat refused by the monitoring service: HTTP %s", exc.response.status_code)
    except httpx.HTTPError as exc:
        logger.warning("Worker heartbeat could not reach the monitoring service: %s", type(exc).__name__)


async def run_heartbeat(
    client: httpx.AsyncClient,
    url: str,
    progress: LoopProgress,
    stopping: asyncio.Event,
    *,
    every: float,
    stuck_after: float,
) -> None:
    """Pings `url` every `every` seconds until `stopping` is set, except while the loop has been
    idle for more than `stuck_after` seconds: then the silence makes the service alert. A failed
    ping is logged and retried on the next beat; it never stops the worker."""
    stuck = False
    while not stopping.is_set():
        if progress.idle_for() > stuck_after:
            if not stuck:
                logger.error(
                    "The worker's loop hasn't moved for %.0f s: its heartbeat stops until it does", progress.idle_for()
                )
            stuck = True
        else:
            if stuck:
                logger.info("The worker's loop is moving again: heartbeat resumed")
            stuck = False
            await _ping(client, url)
        try:
            await asyncio.wait_for(stopping.wait(), timeout=every)
        except TimeoutError:
            pass
