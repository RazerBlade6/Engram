"""Background worker.

Long-running jobs (ingesting a textbook, generating a chapter's cards) run here rather
than in the API. The worker claims jobs from the Postgres queue in `engram.worker.queue`,
runs the handler registered for the job's kind, and shuts down cleanly on SIGINT/SIGTERM.

Reading textbooks and making cards run in separate workers, so a student's cards never wait
behind a book that takes an hour to read, and every job has its own time limit (D92).
"""

import asyncio
import contextlib
import logging
import os
import signal
import socket
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import timedelta
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

INGEST = "ingest_material"
CARDS = "generate_cards"
# The workers, by the kinds of job each takes: one reads materials, one makes cards.
WORKERS: dict[str, tuple[str, ...]] = {"ingest": (INGEST,), "cards": (CARDS,)}


@dataclass(frozen=True)
class Limit:
    time: timedelta
    # Whether a job that runs out of time is tried again: a book too long to read in time
    # will be too long again, while a chapter's cards may only have met a slow model.
    retry: bool


TIME_LIMITS = {
    INGEST: Limit(timedelta(hours=2, minutes=30), retry=False),
    CARDS: Limit(timedelta(minutes=30), retry=True),
}
DEFAULT_LIMIT = Limit(timedelta(minutes=30), retry=True)


def limit_for(kind: str) -> Limit:
    return TIME_LIMITS.get(kind, DEFAULT_LIMIT)


class TimedOut(Exception):
    """The job ran past its time limit. Its error text starts `TimedOut:`, which the database
    shows on a material as 'stalled' (migration job_time_limits)."""


def build_handlers(settings: Settings) -> dict[str, Handler]:
    from engram.cards import job as cards
    from engram.ingest import job as ingest

    return {ingest.KIND: ingest.make_handler(settings), cards.KIND: cards.make_handler(settings)}


class JobLost(Exception):
    """The job was cancelled, or reclaimed by another worker, while it ran."""


async def _run_held(conn: AsyncConnection[Any], job: Job, worker_id: str, handler: Handler) -> None:
    """Run the handler while renewing the job's lock, so only a dead worker's job looks
    stale. If the lock stops renewing, the handler is cancelled and JobLost raised. The
    renewal is stopped with an event rather than cancelled, so a renewal in flight on the
    shared connection always finishes."""
    work: asyncio.Task[None] = asyncio.ensure_future(handler(job))
    done = asyncio.Event()
    renewal = asyncio.create_task(_renew(conn, job, worker_id, done, work))
    try:
        await work
    except asyncio.CancelledError:
        if renewal.done() and renewal.result():
            raise JobLost(f"job {job.id} is no longer locked by {worker_id}") from None
        raise
    finally:
        done.set()
        await renewal


async def _renew(
    conn: AsyncConnection[Any],
    job: Job,
    worker_id: str,
    done: asyncio.Event,
    work: asyncio.Task[None],
) -> bool:
    """Renew the lock every HEARTBEAT until `done`. Returns True if the lock was lost, after
    cancelling `work`."""
    while not done.is_set():
        with contextlib.suppress(TimeoutError):
            await asyncio.wait_for(done.wait(), timeout=queue.HEARTBEAT.total_seconds())
            return False
        try:
            held = await queue.heartbeat(conn, job, worker_id)
        except Exception:
            logger.exception("heartbeat for job %s failed", job.id)
            continue
        if not held:
            work.cancel()
            return True
    return False


async def run_once(
    conn: AsyncConnection[Any],
    worker_id: str,
    handlers: dict[str, Handler],
    kinds: queue.Kinds = None,
) -> bool:
    """Claim and run at most one job, of one of `kinds` (any kind if None). Returns True if a
    job ran."""
    job = await queue.claim(conn, worker_id, kinds)
    if job is None:
        return False
    handler = handlers.get(job.kind)
    limit = limit_for(job.kind)
    try:
        if handler is None:
            raise LookupError(f"no handler for job kind {job.kind!r}")
        try:
            async with asyncio.timeout(limit.time.total_seconds()):
                await _run_held(conn, job, worker_id, handler)
        except TimeoutError:
            raise TimedOut(f"ran longer than its limit of {limit.time}") from None
    except JobLost:
        logger.warning("job %s (%s) was cancelled or taken over; stopped it", job.id, job.kind)
    except Exception as exc:
        permanent = isinstance(exc, PermanentError | LookupError) or (
            isinstance(exc, TimedOut) and not limit.retry
        )
        logger.exception(
            "job %s (%s) failed on attempt %s%s",
            job.id,
            job.kind,
            job.attempts,
            " (permanent)" if permanent else "",
        )
        await queue.fail(conn, job, worker_id, f"{type(exc).__name__}: {exc}", permanent=permanent)
    else:
        await queue.complete(conn, job, worker_id)
        logger.info("job %s (%s) succeeded", job.id, job.kind)
    return True


async def run(
    stop: asyncio.Event,
    conn: AsyncConnection[Any],
    poll_interval: float,
    handlers: dict[str, Handler],
    kinds: queue.Kinds = None,
    name: str = "",
) -> None:
    worker_id = f"{socket.gethostname()}:{os.getpid()}" + (f":{name}" if name else "")
    logger.info("worker %s started", worker_id)
    while not stop.is_set():
        if await run_once(conn, worker_id, handlers, kinds):
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
    kinds: queue.Kinds = None,
    name: str = "",
    reconnect_after: float = RECONNECT_AFTER,
) -> None:
    """`run` until stopped, reconnecting whenever the database drops the connection (a
    restart, a failover). A job cut off that way is picked up again once its lock is stale."""
    while not stop.is_set():
        try:
            async with await connect() as conn:
                await run(stop, conn, poll_interval, handlers, kinds, name)
        except psycopg.OperationalError as exc:
            logger.warning("lost the database (%s); reconnecting in %ss", exc, reconnect_after)
            with contextlib.suppress(TimeoutError):
                await asyncio.wait_for(stop.wait(), timeout=reconnect_after)


async def drain(
    settings: Settings, worker_id: str, kinds: tuple[str, ...], budget: timedelta
) -> int:
    """Run jobs of `kinds` until none is ready, then return how many ran. Used where the worker
    scales to zero (Modal): it starts when woken, empties the queue and stops. Within `budget`
    (the function's own time limit), it claims a job only if that job's limit still fits, so
    the platform never stops one midway; the next sweep starts a new drain for the rest."""
    handlers = build_handlers(settings)
    needs = max(limit_for(kind).time for kind in kinds)
    until = time.monotonic() + budget.total_seconds()
    ran = 0
    async with await AsyncConnection.connect(settings.database_url, autocommit=True) as conn:
        while time.monotonic() + needs.total_seconds() <= until:
            if not await run_once(conn, worker_id, handlers, kinds):
                break
            ran += 1
    return ran


async def _main() -> None:
    settings = get_settings()
    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, stop.set)
    handlers = build_handlers(settings)
    # One loop per worker, as in production: cards are made while a textbook is read. Reading
    # runs in a thread, so it doesn't hold up the other loop.
    await asyncio.gather(
        *(
            serve(
                stop,
                lambda: AsyncConnection.connect(settings.database_url, autocommit=True),
                settings.worker_poll_interval_seconds,
                handlers,
                kinds=kinds,
                name=name,
            )
            for name, kinds in WORKERS.items()
        )
    )


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    asyncio.run(_main())


__all__ = [
    "WORKERS",
    "Job",
    "TimedOut",
    "build_handlers",
    "drain",
    "limit_for",
    "main",
    "run",
    "run_once",
    "serve",
]


if __name__ == "__main__":
    main()
