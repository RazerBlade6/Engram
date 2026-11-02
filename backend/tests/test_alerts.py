from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from email.message import EmailMessage
from typing import Any

import psycopg
import pytest
from fastapi.testclient import TestClient
from psycopg import AsyncConnection

from engram import alerts
from engram.api.errors import describe, route_of
from engram.api.main import create_app
from engram.config import Settings

CONFIGURED = Settings(alert_email="ops@example.com", smtp_host="smtp.example.com")


class Outbox:
    def __init__(self) -> None:
        self.sent: list[EmailMessage] = []

    def __call__(self, settings: Settings, message: EmailMessage) -> None:
        self.sent.append(message)


@pytest.fixture(autouse=True)
async def quiet(conn: AsyncConnection[Any]) -> None:
    """Hide existing failures, errors and spend from these tests; rolled back afterwards."""
    for table in ("jobs", "api_errors", "alerts_sent", "llm_usage"):
        await conn.execute(f"delete from public.{table}")


async def failed_job(conn: AsyncConnection[Any], error: str = "NoCards: all dropped") -> int:
    cur = await conn.execute(
        "insert into public.jobs (kind, status, attempts, last_error)"
        " values ('generate_cards', 'failed', 3, %s) returning id",
        (error,),
    )
    row = await cur.fetchone()
    assert row is not None
    return int(row[0])


async def test_a_failed_job_is_emailed_once(conn: AsyncConnection[Any]) -> None:
    job = await failed_job(conn)
    outbox = Outbox()
    assert await alerts.check(conn, CONFIGURED, sender=outbox) == 1
    [message] = outbox.sent
    assert message["To"] == "ops@example.com"
    assert "failed jobs (1)" in message["Subject"]
    assert f"Job {job} (generate_cards) failed" in message.get_content()
    assert "after 3 attempts: NoCards: all dropped" in message.get_content()

    assert await alerts.check(conn, CONFIGURED, sender=outbox) == 0
    assert len(outbox.sent) == 1


async def test_nothing_is_sent_or_remembered_without_email_settings(
    conn: AsyncConnection[Any],
) -> None:
    await failed_job(conn)
    outbox = Outbox()
    assert await alerts.check(conn, Settings(alert_email=None), sender=outbox) == 0
    assert outbox.sent == []
    # Once configured, the alert still goes out.
    assert await alerts.check(conn, CONFIGURED, sender=outbox) == 1


async def test_a_failed_send_is_tried_again(conn: AsyncConnection[Any]) -> None:
    await failed_job(conn)

    def broken(settings: Settings, message: EmailMessage) -> None:
        raise OSError("connection refused")

    with pytest.raises(OSError):
        await alerts.check(conn, CONFIGURED, sender=broken)
    outbox = Outbox()
    assert await alerts.check(conn, CONFIGURED, sender=outbox) == 1


async def test_old_failures_and_cancelled_jobs_are_ignored(conn: AsyncConnection[Any]) -> None:
    await conn.execute(
        "insert into public.jobs (kind, status, updated_at) values"
        " ('generate_cards', 'failed', now() - interval '8 days'),"
        " ('ingest_material', 'cancelled', now())"
    )
    assert await alerts.check(conn, CONFIGURED, sender=Outbox()) == 0


async def test_a_job_waiting_too_long_is_reported(conn: AsyncConnection[Any]) -> None:
    await conn.execute(
        "insert into public.jobs (kind, run_after) values"
        " ('ingest_material', now() - interval '2 hours'),"
        " ('generate_cards', now() - interval '5 minutes')"
    )
    outbox = Outbox()
    assert await alerts.check(conn, CONFIGURED, sender=outbox) == 1
    body = outbox.sent[0].get_content()
    assert "(ingest_material) has been waiting to start" in body
    assert "generate_cards" not in body


async def test_api_errors_are_grouped(conn: AsyncConnection[Any]) -> None:
    await conn.execute(
        "insert into public.api_errors (method, route, status, error) values"
        " ('GET', '/review/queue', 500, 'KeyError at engram/review.py:10'),"
        " ('GET', '/review/queue', 500, 'KeyError at engram/review.py:10'),"
        " ('POST', '/courses/{course_id}/ask', null, 'ProviderError at engram/chat/answer.py:5')"
    )
    outbox = Outbox()
    assert await alerts.check(conn, CONFIGURED, sender=outbox) == 2
    message = outbox.sent[0]
    assert "api errors (3)" in message["Subject"]
    body = message.get_content()
    assert "GET /review/queue: KeyError at engram/review.py:10 (2 times," in body
    assert "POST /courses/{course_id}/ask: ProviderError" in body
    assert await alerts.check(conn, CONFIGURED, sender=outbox) == 0


async def usage(conn: AsyncConnection[Any], model: str, input_tokens: int, output: int) -> None:
    await conn.execute(
        "insert into public.llm_usage (job, model, requests, input_tokens, output_tokens)"
        " values ('generate_cards', %s, 1, %s, %s)",
        (model, input_tokens, output),
    )


async def test_spend_over_the_daily_level_is_reported_once_a_day(
    conn: AsyncConnection[Any],
) -> None:
    # $4 + $2 = $6 on Opus: over the $5 daily level, under the $30 monthly one.
    await usage(conn, "claude-opus-5-5", 1_000_000, 100_000)
    outbox = Outbox()
    assert await alerts.check(conn, CONFIGURED, sender=outbox) == 1
    assert "spend today (UTC) is about $6.00, over the $5.00" in outbox.sent[0].get_content()
    await usage(conn, "claude-opus-5-5", 1_000_000, 0)
    assert await alerts.check(conn, CONFIGURED, sender=outbox) == 0


async def test_spend_over_the_monthly_level(conn: AsyncConnection[Any]) -> None:
    await usage(conn, "claude-opus-5-5", 1_000_000, 0)
    now = datetime.now(UTC)
    if now.day > 1:
        # Earlier this month: counts towards the month, not today.
        await conn.execute(
            "update public.llm_usage set created_at = date_trunc('month', now() at time zone"
            " 'utc') at time zone 'utc'"
        )
    settings = CONFIGURED.model_copy(update={"alert_monthly_spend_usd": 3.0})
    outbox = Outbox()
    assert await alerts.check(conn, settings, sender=outbox) == 1
    assert "spend this month (UTC) is about $4.00" in outbox.sent[0].get_content()


def test_prices() -> None:
    assert alerts.price_of("claude-haiku-5-5").output == 0.50
    # A job that used several models is priced as the dearest; an unknown one as the dearest.
    assert alerts.price_of("claude-haiku-5-5, claude-sonnet-5-5").output == 10.00
    assert alerts.price_of("some-new-model").output == 20.00


def test_describe_names_the_line_in_engram() -> None:
    try:
        {}["missing"]
    except KeyError as exc:
        described = describe(exc)
    assert described.startswith("KeyError at ")
    assert described.endswith(".py:" + described.rsplit(":", 1)[1])


def test_route_of_hides_ids() -> None:
    scope = {"path": "/courses/3f1c2b9e-1d2a-4c3b-9a8e-0b1c2d3e4f50/materials/12"}
    assert route_of(scope) == "/courses/{id}/materials/{id}"


@pytest.fixture
def failing_client(database_url: str) -> Iterator[TestClient]:
    app = create_app()

    @app.get("/test-boom/{thing_id}")
    def boom(thing_id: str) -> None:
        raise RuntimeError("secret user text")

    with TestClient(app, raise_server_exceptions=False) as c:
        yield c
    with psycopg.connect(database_url, autocommit=True) as c:
        c.execute("delete from public.api_errors where route like '/test-boom%%'")


def test_the_api_records_a_server_error_without_its_message(
    failing_client: TestClient, database_url: str
) -> None:
    started = datetime.now(UTC) - timedelta(seconds=5)
    assert failing_client.get("/test-boom/abc").status_code == 500
    assert failing_client.get("/health").status_code == 200
    with psycopg.connect(database_url) as c:
        rows = c.execute(
            "select method, route, status, error from public.api_errors"
            " where route like '/test-boom%%' and created_at > %s",
            (started,),
        ).fetchall()
    [(method, route, status, error)] = rows
    assert (method, route, status) == ("GET", "/test-boom/{thing_id}", 500)
    assert error.startswith("RuntimeError at ") and "secret" not in error
