from collections.abc import Callable
from datetime import timedelta
from typing import Any

import pytest
from psycopg import AsyncConnection

from engram.worker import queue


@pytest.fixture(autouse=True)
async def empty_queue(conn: AsyncConnection[Any]) -> None:
    """Hide any existing jobs from this test; the delete is rolled back with the test."""
    await conn.execute("delete from public.jobs")


async def status_of(conn: AsyncConnection[Any], job_id: int) -> tuple[Any, ...]:
    cur = await conn.execute(
        "select status::text, attempts, run_after > now(), last_error from public.jobs"
        " where id = %s",
        (job_id,),
    )
    row = await cur.fetchone()
    assert row is not None
    return tuple(row)


async def test_claim_complete(conn: AsyncConnection[Any]) -> None:
    job_id = await queue.enqueue(conn, "test", {"x": 1})
    job = await queue.claim(conn, "w1")
    assert job is not None and job.id == job_id
    assert job.payload == {"x": 1} and job.attempts == 1
    assert await queue.claim(conn, "w2") is None
    await queue.complete(conn, job, "w1")
    assert (await status_of(conn, job_id))[0] == "succeeded"


async def test_fail_requeues_with_backoff_then_gives_up(conn: AsyncConnection[Any]) -> None:
    job_id = await queue.enqueue(conn, "test")
    job = await queue.claim(conn, "w1")
    assert job is not None and job.id == job_id

    await queue.fail(conn, job, "w1", "boom")
    status, attempts, delayed, error = await status_of(conn, job_id)
    assert (status, attempts, delayed, error) == ("queued", 1, True, "boom")

    # Exhaust the remaining attempts, skipping the backoff delay each time.
    for _ in range(job.max_attempts - 1):
        await conn.execute("update public.jobs set run_after = now() where id = %s", (job_id,))
        job = await queue.claim(conn, "w1")
        assert job is not None
        await queue.fail(conn, job, "w1", "boom")
    assert (await status_of(conn, job_id))[0] == "failed"


async def test_has_ready_skips_jobs_waiting_for_backoff(conn: AsyncConnection[Any]) -> None:
    assert not await queue.has_ready(conn)
    await queue.enqueue(conn, "test")
    assert await queue.has_ready(conn)
    job = await queue.claim(conn, "w1")
    assert job is not None and not await queue.has_ready(conn)
    await queue.fail(conn, job, "w1", "boom")
    assert not await queue.has_ready(conn)


async def test_stale_running_job_is_reclaimed(conn: AsyncConnection[Any]) -> None:
    job_id = await queue.enqueue(conn, "test")
    assert await queue.claim(conn, "dead-worker") is not None
    await conn.execute(
        "update public.jobs set locked_at = now() - %s where id = %s",
        (queue.STALE_LOCK + timedelta(minutes=1), job_id),
    )
    job = await queue.claim(conn, "w2")
    assert job is not None and job.id == job_id and job.attempts == 2


async def test_concurrent_workers_never_share_a_job(database_url: str) -> None:
    async with (
        await AsyncConnection.connect(database_url, autocommit=True) as setup,
        await AsyncConnection.connect(database_url) as a,
        await AsyncConnection.connect(database_url) as b,
    ):
        ids = {await queue.enqueue(setup, "test:concurrency") for _ in range(2)}
        try:
            job_a = await queue.claim(a, "a")  # a's transaction holds its row lock
            job_b = await queue.claim(b, "b")
            assert job_a is not None and job_b is not None
            assert {job_a.id, job_b.id} == ids
        finally:
            await a.rollback()
            await b.rollback()
            await setup.execute("delete from public.jobs where id = any(%s)", (list(ids),))


async def test_heartbeat_renews_only_the_holders_lock(conn: AsyncConnection[Any]) -> None:
    job_id = await queue.enqueue(conn, "test")
    job = await queue.claim(conn, "w1")
    assert job is not None and job.id == job_id
    await conn.execute(
        "update public.jobs set locked_at = now() - %s where id = %s",
        (queue.STALE_LOCK - timedelta(minutes=1), job_id),
    )
    assert not await queue.heartbeat(conn, job, "someone-else")
    assert await queue.heartbeat(conn, job, "w1")
    # Renewed, so a sweep a minute later doesn't take it.
    await conn.execute(
        "update public.jobs set locked_at = locked_at - interval '1 minute' where id = %s",
        (job_id,),
    )
    assert await queue.claim(conn, "w2") is None


async def test_a_cancelled_or_reclaimed_job_is_not_finished_by_its_old_worker(
    conn: AsyncConnection[Any],
) -> None:
    job_id = await queue.enqueue(conn, "test")
    job = await queue.claim(conn, "w1")
    assert job is not None
    await conn.execute("update public.jobs set status = 'cancelled' where id = %s", (job_id,))
    await queue.complete(conn, job, "w1")
    await queue.fail(conn, job, "w1", "boom")
    assert (await status_of(conn, job_id))[0] == "cancelled"
    assert not await queue.heartbeat(conn, job, "w1")

    await conn.execute(
        "update public.jobs set status = 'running', locked_by = 'w2' where id = %s", (job_id,)
    )
    await queue.complete(conn, job, "w1")
    assert (await status_of(conn, job_id))[0] == "running"


async def test_removing_a_material_cancels_its_jobs(
    database_url: str, make_user: Callable[..., str]
) -> None:
    # Committed rather than rolled back: the user's cleanup must see the course.
    async with await AsyncConnection.connect(database_url, autocommit=True) as c:
        cur = await c.execute(
            "insert into public.courses (owner_id, title) values (%s, 'Bio') returning id",
            (make_user(),),
        )
        course = (await cur.fetchone() or [None])[0]
        cur = await c.execute(
            "insert into public.materials (course_id, kind, title, storage_path)"
            " values (%s, 'textbook', 'Biology', 'x/y/biology.pdf') returning id",
            (course,),
        )
        material = (await cur.fetchone() or [None])[0]
        cur = await c.execute(
            "insert into public.sections (material_id, ordinal, level, title)"
            " values (%s, 0, 1, 'Chapter 1') returning id",
            (material,),
        )
        section = (await cur.fetchone() or [None])[0]
        jobs = [
            await queue.enqueue(c, "ingest_material", {"material_id": str(material)}),
            await queue.enqueue(c, "generate_cards", {"section_id": str(section)}),
            await queue.enqueue(c, "ingest_material", {"material_id": "another"}),
        ]
        try:
            await c.execute(
                "update public.jobs set status = 'running', locked_by = 'w1' where id = %s",
                (jobs[0],),
            )
            await c.execute("delete from public.materials where id = %s", (material,))
            statuses = [(await status_of(c, j))[0] for j in jobs]
            assert statuses == ["cancelled", "cancelled", "queued"]
        finally:
            await c.execute("delete from public.jobs where id = any(%s)", (jobs,))
