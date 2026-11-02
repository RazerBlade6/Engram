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


async def test_a_cancelled_job_stops_within_a_heartbeat(
    conn: AsyncConnection[Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(queue, "HEARTBEAT", timedelta(milliseconds=20))
    stopped = asyncio.Event()

    async def long(job: Job) -> None:
        await conn.execute("update public.jobs set status = 'cancelled' where id = %s", (job.id,))
        try:
            await asyncio.sleep(10)
        finally:
            stopped.set()

    await conn.execute("delete from public.jobs")
    job_id = await queue.enqueue(conn, "long")
    assert await asyncio.wait_for(run_once(conn, "w", {"long": long}), timeout=2)
    assert stopped.is_set()
    cur = await conn.execute("select status::text from public.jobs where id = %s", (job_id,))
    assert await cur.fetchone() == ("cancelled",)


async def test_each_worker_has_its_kinds() -> None:
    from engram.cards import job as cards
    from engram.ingest import job as ingest

    assert main.WORKERS == {"ingest": (ingest.KIND,), "cards": (cards.KIND,)}


async def test_a_job_past_its_time_limit_fails(
    conn: AsyncConnection[Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    """D92: each job has its own limit; a kind that wouldn't do better next time isn't retried."""
    monkeypatch.setattr(
        main,
        "TIME_LIMITS",
        {
            "slow-retry": main.Limit(timedelta(milliseconds=50), retry=True),
            "slow-once": main.Limit(timedelta(milliseconds=50), retry=False),
        },
    )

    async def slow(job: Job) -> None:
        await asyncio.sleep(10)

    await conn.execute("delete from public.jobs")
    retried = await queue.enqueue(conn, "slow-retry")
    given_up = await queue.enqueue(conn, "slow-once")
    handlers = {"slow-retry": slow, "slow-once": slow}
    assert await run_once(conn, "w", handlers)
    assert await run_once(conn, "w", handlers)
    cur = await conn.execute(
        "select id, status::text, last_error from public.jobs where id = any(%s) order by id",
        ([retried, given_up],),
    )
    limit = "TimedOut: ran longer than its limit of 0:00:00.050000"
    assert await cur.fetchall() == [(retried, "queued", limit), (given_up, "failed", limit)]


async def test_cards_are_made_while_a_textbook_is_read(database_url: str) -> None:
    """D92: two workers, one per kind, as locally and on Modal."""
    reading = asyncio.Event()
    finish_reading = asyncio.Event()
    made: list[int] = []

    async def read(job: Job) -> None:
        reading.set()
        await finish_reading.wait()

    async def make_cards(job: Job) -> None:
        made.append(job.id)

    kinds = {"book": ("test-book",), "cards": ("test-cards",)}
    with psycopg.connect(database_url, autocommit=True) as c:
        book = c.execute("insert into public.jobs (kind) values ('test-book') returning id")
        book_row = book.fetchone()
        cards = c.execute("insert into public.jobs (kind) values ('test-cards') returning id")
        cards_row = cards.fetchone()
    assert book_row and cards_row
    stop = asyncio.Event()

    def connect() -> Any:
        return AsyncConnection.connect(database_url, autocommit=True)

    handlers = {"test-book": read, "test-cards": make_cards}
    loops = [
        asyncio.create_task(serve(stop, connect, 0.02, handlers, kinds=k, name=n))
        for n, k in kinds.items()
    ]
    try:
        await asyncio.wait_for(reading.wait(), timeout=5)
        for _ in range(100):
            if made:
                break
            await asyncio.sleep(0.05)
        # The book is still being read, and the chapter's cards are already made.
        assert made == [cards_row[0]] and not finish_reading.is_set()
    finally:
        finish_reading.set()
        stop.set()
        await asyncio.wait_for(asyncio.gather(*loops), timeout=5)
        with psycopg.connect(database_url, autocommit=True) as c:
            c.execute("delete from public.jobs where kind in ('test-book', 'test-cards')")


async def test_a_drain_claims_only_jobs_whose_limit_fits(
    database_url: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    ran: list[str] = []

    async def handler(job: Job) -> None:
        ran.append(job.kind)

    monkeypatch.setattr(main, "build_handlers", lambda settings: {"test-drain": handler})
    monkeypatch.setattr(
        main, "TIME_LIMITS", {"test-drain": main.Limit(timedelta(minutes=10), retry=True)}
    )
    settings = main.Settings(database_url=database_url)
    with psycopg.connect(database_url, autocommit=True) as c:
        c.execute("insert into public.jobs (kind) values ('test-drain'), ('test-drain')")
    try:
        # Too little time left for a job that may take ten minutes: none is started.
        assert await main.drain(settings, "w", ("test-drain",), timedelta(minutes=5)) == 0
        assert await main.drain(settings, "w", ("test-drain",), timedelta(minutes=30)) == 2
        assert ran == ["test-drain", "test-drain"]
    finally:
        with psycopg.connect(database_url, autocommit=True) as c:
            c.execute("delete from public.jobs where kind = 'test-drain'")
