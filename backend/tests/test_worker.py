import asyncio
from datetime import timedelta
from typing import Any

import psycopg
import pytest
from psycopg import AsyncConnection

from engram.worker import main, queue
from engram.worker.main import run, run_once, serve
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


async def test_a_running_job_keeps_its_lock(
    conn: AsyncConnection[Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(queue, "HEARTBEAT", timedelta(milliseconds=20))
    renewed: list[Any] = []

    async def slow(job: Job) -> None:
        # Age the lock, then give the heartbeat a few beats to renew it.
        await conn.execute(
            "update public.jobs set locked_at = now() - interval '1 hour' where id = %s",
            (job.id,),
        )
        await asyncio.sleep(0.1)
        cur = await conn.execute(
            "select locked_at > now() - interval '1 minute' from public.jobs where id = %s",
            (job.id,),
        )
        renewed.append(await cur.fetchone())

    await conn.execute("delete from public.jobs")
    job_id = await queue.enqueue(conn, "slow")
    assert await run_once(conn, "w", {"slow": slow})
    assert renewed == [(True,)]
    cur = await conn.execute(
        "select status::text, locked_at from public.jobs where id = %s", (job_id,)
    )
    assert await cur.fetchone() == ("succeeded", None)


class FakeConnection:
    async def __aenter__(self) -> "FakeConnection":
        return self

    async def __aexit__(self, *exc: object) -> None:
        pass


async def test_the_worker_reconnects_when_the_database_drops_it(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    stop = asyncio.Event()
    connections: list[FakeConnection] = []
    runs: list[FakeConnection] = []

    async def connect() -> FakeConnection:
        connections.append(FakeConnection())
        return connections[-1]

    async def fake_run(stop: asyncio.Event, conn: Any, *args: object) -> None:
        runs.append(conn)
        if len(runs) == 1:
            raise psycopg.errors.AdminShutdown("terminating connection")
        stop.set()

    monkeypatch.setattr(main, "run", fake_run)
    await asyncio.wait_for(
        serve(stop, connect, 10, {}, reconnect_after=0.01),  # type: ignore[arg-type]
        timeout=1,
    )
    assert len(connections) == 2
    assert runs == connections  # a fresh connection for the second run
