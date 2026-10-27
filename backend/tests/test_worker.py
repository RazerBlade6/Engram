import asyncio
from typing import Any

from psycopg import AsyncConnection

from engram.worker import queue
from engram.worker.main import run, run_once
from engram.worker.queue import Job


async def test_run_once_completes_job(conn: AsyncConnection[Any]) -> None:
    seen: list[Job] = []

    async def handler(job: Job) -> None:
        seen.append(job)

    await conn.execute("delete from public.jobs")  # rolled back after the test
    job_id = await queue.enqueue(conn, "test", {"n": 1})
    assert await run_once(conn, "w", {"test": handler})
    assert [j.id for j in seen] == [job_id]
    cur = await conn.execute("select status::text from public.jobs where id = %s", (job_id,))
    assert await cur.fetchone() == ("succeeded",)


async def test_run_once_records_failure_and_unknown_kinds(conn: AsyncConnection[Any]) -> None:
    async def broken(job: Job) -> None:
        raise ValueError("bad input")

    await conn.execute("delete from public.jobs")
    failing = await queue.enqueue(conn, "broken")
    unknown = await queue.enqueue(conn, "unknown")
    assert await run_once(conn, "w", {"broken": broken})
    assert await run_once(conn, "w", {"broken": broken})
    cur = await conn.execute(
        "select id, last_error from public.jobs where id = any(%s) order by id",
        ([failing, unknown],),
    )
    assert await cur.fetchall() == [
        (failing, "ValueError: bad input"),
        (unknown, "LookupError: no handler for job kind 'unknown'"),
    ]


async def test_run_once_with_empty_queue(conn: AsyncConnection[Any]) -> None:
    await conn.execute("delete from public.jobs")  # rolled back after the test
    assert not await run_once(conn, "w", {})


async def test_worker_stops_when_signalled(conn: AsyncConnection[Any]) -> None:
    await conn.execute("delete from public.jobs")
    stop = asyncio.Event()
    task = asyncio.create_task(run(stop, conn, poll_interval=10, handlers={}))
    await asyncio.sleep(0.05)
    stop.set()
    await asyncio.wait_for(task, timeout=1)


async def test_permanent_errors_skip_retries(conn: AsyncConnection[Any]) -> None:
    from engram.errors import PermanentError

    async def misconfigured(job: Job) -> None:
        raise PermanentError("no credentials")

    await conn.execute("delete from public.jobs")
    job_id = await queue.enqueue(conn, "needs-key")
    assert await run_once(conn, "w", {"needs-key": misconfigured})
    cur = await conn.execute(
        "select status::text, attempts from public.jobs where id = %s", (job_id,)
    )
    assert await cur.fetchone() == ("failed", 1)
