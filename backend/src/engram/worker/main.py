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
from collections.abc import AsyncIterator, Awaitable, Callable
from typing import Any

import psycopg
from psycopg import AsyncConnection

from engram.config import Settings, get_settings
from engram.errors import PermanentError
from engram.worker import queue
from engram.worker.queue import Handler, Job

logger = logging.getLogger("engram.worker")

# Seconds between attempts to reach the database after losing it.
RECONNECT_AFTER = 5.0


def build_handlers(settings: Settings) -> dict[str, Handler]:
    from engram.cards import job as cards
    from engram.ingest import job as ingest

    return {ingest.KIND: ingest.make_handler(settings), cards.KIND: cards.make_handler(settings)}


@contextlib.asynccontextmanager
async def _keep_alive(conn: AsyncConnection[Any], job: Job, worker_id: str) -> AsyncIterator[None]:
    """Renew the job's lock while the block runs, so only a dead worker's job looks stale.
    Stopped with an event rather than cancelled, so a renewal in flight on the shared
    connection always finishes."""
    done = asyncio.Event()
    task = asyncio.create_task(_renew(conn, job, worker_id, done))
    try:
        yield
    finally:
        done.set()
        await task


async def _renew(conn: AsyncConnection[Any], job: Job, worker_id: str, done: asyncio.Event) -> None:
    while not done.is_set():
        with contextlib.suppress(TimeoutError):
            await asyncio.wait_for(done.wait(), timeout=queue.HEARTBEAT.total_seconds())
            return
        try:
            if not await queue.heartbeat(conn, job, worker_id):
                logger.warning("job %s is no longer locked by %s", job.id, worker_id)
        except Exception:
            logger.exception("heartbeat for job %s failed", job.id)


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
        async with _keep_alive(conn, job, worker_id):
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


async def serve(
    stop: asyncio.Event,
    connect: Callable[[], Awaitable[AsyncConnection[Any]]],
    poll_interval: float,
    handlers: dict[str, Handler],
    *,
    reconnect_after: float = RECONNECT_AFTER,
) -> None:
    """`run` until stopped, reconnecting whenever the database drops the connection (a
    restart, a failover). A job cut off that way is picked up again once its lock is stale."""
    while not stop.is_set():
        try:
            async with await connect() as conn:
                await run(stop, conn, poll_interval, handlers)
        except psycopg.OperationalError as exc:
            logger.warning("lost the database (%s); reconnecting in %ss", exc, reconnect_after)
            with contextlib.suppress(TimeoutError):
                await asyncio.wait_for(stop.wait(), timeout=reconnect_after)


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
    await serve(
        stop,
        lambda: AsyncConnection.connect(settings.database_url, autocommit=True),
        settings.worker_poll_interval_seconds,
        build_handlers(settings),
    )


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    asyncio.run(_main())


__all__ = ["Job", "build_handlers", "drain", "main", "run", "run_once", "serve"]


if __name__ == "__main__":
    main()
