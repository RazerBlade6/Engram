"""Postgres-backed job queue.

Jobs live in `public.jobs`. A worker claims one with `FOR UPDATE SKIP LOCKED`, so several
workers can poll the same table without handing out a job twice. While a job runs, its
worker renews the lock every `HEARTBEAT`; a job left `running` by a worker that died (or was
preempted, as Modal containers can be) is reclaimed once its lock is older than `STALE_LOCK`.
"""

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import timedelta
from typing import Any

from psycopg import AsyncConnection
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

HEARTBEAT = timedelta(minutes=1)
# Several missed heartbeats, so a slow database round trip never looks like a dead worker.
STALE_LOCK = timedelta(minutes=5)
RETRY_BASE_DELAY = timedelta(seconds=30)


@dataclass(frozen=True)
class Job:
    id: int
    kind: str
    payload: dict[str, Any]
    attempts: int
    max_attempts: int


Handler = Callable[[Job], Awaitable[None]]


async def enqueue(
    conn: AsyncConnection[Any], kind: str, payload: dict[str, Any] | None = None
) -> int:
    cur = await conn.execute(
        "insert into public.jobs (kind, payload) values (%s, %s) returning id",
        (kind, Jsonb(payload or {})),
    )
    row = await cur.fetchone()
    assert row is not None
    return int(row[0])


# Jobs a worker may claim now: queued and due, or left running by a worker that died.
READY = """
    (status = 'queued' and run_after <= now())
    or (status = 'running' and locked_at < now() - %(stale)s)
"""


async def has_ready(conn: AsyncConnection[Any]) -> bool:
    cur = await conn.execute(
        f"select exists (select 1 from public.jobs where {READY})", {"stale": STALE_LOCK}
    )
    row = await cur.fetchone()
    return bool(row and row[0])


async def claim(conn: AsyncConnection[Any], worker_id: str) -> Job | None:
    async with conn.cursor(row_factory=dict_row) as cur:
        await cur.execute(
            f"""
            update public.jobs
               set status = 'running', locked_at = now(), locked_by = %(worker)s,
                   attempts = attempts + 1
             where id = (
                   select id from public.jobs
                    where {READY}
                    order by run_after, id
                    for update skip locked
                    limit 1)
            returning id, kind, payload, attempts, max_attempts
            """,
            {"worker": worker_id, "stale": STALE_LOCK},
        )
        row = await cur.fetchone()
    return Job(**row) if row else None


async def heartbeat(conn: AsyncConnection[Any], job: Job, worker_id: str) -> bool:
    """Renew the lock on a running job. False if the job is no longer this worker's."""
    cur = await conn.execute(
        "update public.jobs set locked_at = now()"
        " where id = %s and status = 'running' and locked_by = %s",
        (job.id, worker_id),
    )
    return cur.rowcount == 1


async def complete(conn: AsyncConnection[Any], job: Job) -> None:
    await conn.execute(
        "update public.jobs set status = 'succeeded', locked_at = null, locked_by = null"
        " where id = %s",
        (job.id,),
    )


async def fail(
    conn: AsyncConnection[Any], job: Job, error: str, *, permanent: bool = False
) -> None:
    """Requeue with exponential backoff, or mark failed once attempts are used up (or at once,
    for a permanent error)."""
    if permanent or job.attempts >= job.max_attempts:
        await conn.execute(
            "update public.jobs set status = 'failed', last_error = %s,"
            " locked_at = null, locked_by = null where id = %s",
            (error, job.id),
        )
        return
    delay = RETRY_BASE_DELAY * 2 ** (job.attempts - 1)
    await conn.execute(
        "update public.jobs set status = 'queued', last_error = %s, run_after = now() + %s,"
        " locked_at = null, locked_by = null where id = %s",
        (error, delay, job.id),
    )
