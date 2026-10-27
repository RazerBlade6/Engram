"""Background worker.

Long-running jobs (ingesting a textbook, generating a chapter's cards) run here rather
than in the API. The worker claims jobs from the Postgres queue in `engram.worker.queue`,
runs the handler registered for the job's kind, and shuts down cleanly on SIGINT/SIGTERM.
"""

import asyncio
import contextlib
import logging
import os
import signal
import socket
from typing import Any

from psycopg import AsyncConnection

from engram.config import Settings, get_settings
from engram.errors import PermanentError
from engram.worker import queue
from engram.worker.queue import Handler, Job

logger = logging.getLogger("engram.worker")


def build_handlers(settings: Settings) -> dict[str, Handler]:
    from engram.cards import job as cards
    from engram.ingest import job as ingest

    return {ingest.KIND: ingest.make_handler(settings), cards.KIND: cards.make_handler(settings)}


async def run_once(
    conn: AsyncConnection[Any], worker_id: str, handlers: dict[str, Handler]
) -> bool:
    """Claim and run at most one job. Returns True if a job ran."""
    job = await queue.claim(conn, worker_id)
    if job is None:
        return False
    handler = handlers.get(job.kind)
    try:
        if handler is None:
            raise LookupError(f"no handler for job kind {job.kind!r}")
        await handler(job)
    except Exception as exc:
        permanent = isinstance(exc, PermanentError | LookupError)
        logger.exception(
            "job %s (%s) failed on attempt %s%s",
            job.id,
            job.kind,
            job.attempts,
            " (permanent)" if permanent else "",
        )
        await queue.fail(conn, job, f"{type(exc).__name__}: {exc}", permanent=permanent)
    else:
        await queue.complete(conn, job)
        logger.info("job %s (%s) succeeded", job.id, job.kind)
    return True


async def run(
    stop: asyncio.Event,
    conn: AsyncConnection[Any],
    poll_interval: float,
    handlers: dict[str, Handler],
) -> None:
    worker_id = f"{socket.gethostname()}:{os.getpid()}"
    logger.info("worker %s started", worker_id)
    while not stop.is_set():
        if await run_once(conn, worker_id, handlers):
            continue
        with contextlib.suppress(TimeoutError):
            await asyncio.wait_for(stop.wait(), timeout=poll_interval)
    logger.info("worker %s stopped", worker_id)


async def drain(settings: Settings, worker_id: str) -> int:
    """Run jobs until none is ready, then return how many ran. Used where the worker scales
    to zero (Modal): it starts when woken, empties the queue and stops."""
    handlers = build_handlers(settings)
    ran = 0
    async with await AsyncConnection.connect(settings.database_url, autocommit=True) as conn:
        while await run_once(conn, worker_id, handlers):
            ran += 1
    return ran


async def _main() -> None:
    settings = get_settings()
    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, stop.set)
    async with await AsyncConnection.connect(settings.database_url, autocommit=True) as conn:
        await run(stop, conn, settings.worker_poll_interval_seconds, build_handlers(settings))


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    asyncio.run(_main())


__all__ = ["Job", "build_handlers", "drain", "main", "run", "run_once"]


if __name__ == "__main__":
    main()
