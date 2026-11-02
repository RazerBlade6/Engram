"""Alerts for the operator (D99), emailed when something goes wrong that no user would report.

The worker's sweep runs `check` every 15 minutes (see modal_app.py). It looks for:

- jobs that failed for good: a textbook that couldn't be read, a chapter left without cards;
- jobs still waiting to start long after they were queued: the worker isn't being woken;
- requests the API failed with a server error (recorded by `engram.api.errors`);
- estimated inference spend over a daily or monthly level.

Everything new goes out in one email, and each alert is sent once (`public.alerts_sent`).
Without an address and an SMTP host, alerts are only logged and stay unsent.

    uv run python -m engram.alerts     # one check, now
"""

import asyncio
import logging
import smtplib
from collections import defaultdict
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from email.message import EmailMessage
from typing import Any

from psycopg import AsyncConnection

from engram.config import Settings, get_settings

logger = logging.getLogger(__name__)

# How far back to look for failures not yet reported, and how long to keep the records.
LOOKBACK = timedelta(days=7)
KEEP = timedelta(days=30)
# Longest error text quoted in an email.
ERROR_CHARS = 300


@dataclass(frozen=True)
class Price:
    """US dollars per million tokens."""

    input: float
    output: float
    cache_read: float

    @property
    def cache_write(self) -> float:
        return self.input * 1.25


# Anthropic's list prices. Spend is an estimate for alerting; the provider's console has the
# bill. A model missing here is priced as the most expensive one, so it can't hide spend.
PRICES = {
    "claude-opus-5-5": Price(4.00, 20.00, 0.20),
    "claude-sonnet-5-5": Price(2.00, 10.00, 0.20),
    "claude-haiku-5-5": Price(0.10, 0.50, 0.01),
}
_DEAREST = max(PRICES.values(), key=lambda p: p.output)


def price_of(models: str) -> Price:
    """The price for an `llm_usage.model` value, which lists every model a job used: the
    dearest of them, since the split between them isn't recorded."""
    prices = [PRICES.get(m.strip(), _DEAREST) for m in models.split(",")]
    return max(prices, key=lambda p: p.output)


async def spend_since(conn: AsyncConnection[Any], since: datetime) -> float:
    cur = await conn.execute(
        "select model, sum(input_tokens)::float8, sum(output_tokens)::float8,"
        " sum(cache_read_input_tokens)::float8, sum(cache_creation_input_tokens)::float8"
        " from public.llm_usage where created_at >= %s"
        " group by model",
        (since,),
    )
    total = 0.0
    for model, fresh, output, read, written in await cur.fetchall():
        p = price_of(model)
        total += (
            fresh * p.input + output * p.output + read * p.cache_read + written * p.cache_write
        ) / 1_000_000
    return total


@dataclass(frozen=True)
class Alert:
    kind: str
    keys: tuple[str, ...]
    text: str


def _when(at: datetime) -> str:
    return at.astimezone(UTC).strftime("%d %b %H:%M UTC")


async def _failed_jobs(conn: AsyncConnection[Any], now: datetime) -> list[Alert]:
    cur = await conn.execute(
        "select j.id, j.kind, j.attempts, j.updated_at, j.last_error from public.jobs j"
        " where j.status = 'failed' and j.updated_at > %s and not exists ("
        "   select 1 from public.alerts_sent a"
        "    where a.kind = 'job_failed' and a.key = j.id::text)"
        " order by j.id",
        (now - LOOKBACK,),
    )
    return [
        Alert(
            "job_failed",
            (str(id_),),
            f"Job {id_} ({kind}) failed {_when(at)} after {attempts} attempt"
            f"{'' if attempts == 1 else 's'}: {(error or 'no error recorded')[:ERROR_CHARS]}",
        )
        for id_, kind, attempts, at, error in await cur.fetchall()
    ]


async def _waiting_jobs(conn: AsyncConnection[Any], now: datetime, wait: timedelta) -> list[Alert]:
    cur = await conn.execute(
        "select j.id, j.kind, j.run_after from public.jobs j"
        " where j.status = 'queued' and j.run_after < %s and j.created_at > %s"
        " and not exists ("
        "   select 1 from public.alerts_sent a"
        "    where a.kind = 'job_waiting' and a.key = j.id::text)"
        " order by j.id",
        (now - wait, now - LOOKBACK),
    )
    return [
        Alert(
            "job_waiting",
            (str(id_),),
            f"Job {id_} ({kind}) has been waiting to start since {_when(since)}: the worker"
            " may not be waking, or another job is holding it up.",
        )
        for id_, kind, since in await cur.fetchall()
    ]


async def _api_errors(conn: AsyncConnection[Any], now: datetime) -> list[Alert]:
    cur = await conn.execute(
        "select e.id, e.method, e.route, e.error, e.created_at from public.api_errors e"
        " where e.created_at > %s and not exists ("
        "   select 1 from public.alerts_sent a"
        "    where a.kind = 'api_error' and a.key = e.id::text)"
        " order by e.id",
        (now - LOOKBACK,),
    )
    groups: dict[tuple[str, str, str], list[tuple[int, datetime]]] = defaultdict(list)
    for id_, method, route, error, at in await cur.fetchall():
        groups[(method, route, error)].append((id_, at))
    alerts = []
    for (method, route, error), rows in groups.items():
        times = (
            f"{_when(rows[0][1])}"
            if len(rows) == 1
            else (f"{len(rows)} times, {_when(rows[0][1])} to {_when(rows[-1][1])}")
        )
        alerts.append(
            Alert(
                "api_error",
                tuple(str(id_) for id_, _ in rows),
                f"{method} {route}: {error} ({times}). The traceback is in the API's logs.",
            )
        )
    return alerts


async def _spend(conn: AsyncConnection[Any], now: datetime, settings: Settings) -> list[Alert]:
    day = now.astimezone(UTC).replace(hour=0, minute=0, second=0, microsecond=0)
    month = day.replace(day=1)
    periods = [
        ("spend_day", day.strftime("%Y-%m-%d"), day, settings.alert_daily_spend_usd, "today"),
        (
            "spend_month",
            month.strftime("%Y-%m"),
            month,
            settings.alert_monthly_spend_usd,
            "this month",
        ),
    ]
    alerts = []
    for kind, key, since, level, label in periods:
        cur = await conn.execute(
            "select 1 from public.alerts_sent where kind = %s and key = %s", (kind, key)
        )
        if await cur.fetchone() is not None:
            continue
        spent = await spend_since(conn, since)
        if spent > level:
            alerts.append(
                Alert(
                    kind,
                    (key,),
                    f"Inference spend {label} (UTC) is about ${spent:.2f}, over the"
                    f" ${level:.2f} alert level.",
                )
            )
    return alerts


async def collect(conn: AsyncConnection[Any], settings: Settings, now: datetime) -> list[Alert]:
    """Every alert not yet sent."""
    wait = timedelta(minutes=settings.alert_job_wait_minutes)
    return [
        *await _failed_jobs(conn, now),
        *await _waiting_jobs(conn, now, wait),
        *await _api_errors(conn, now),
        *await _spend(conn, now, settings),
    ]


_HEADINGS = {
    "job_failed": "Failed jobs",
    "job_waiting": "Jobs not starting",
    "api_error": "API errors",
    "spend_day": "Inference spend",
    "spend_month": "Inference spend",
}


def compose(alerts: list[Alert], settings: Settings) -> EmailMessage:
    counts: dict[str, int] = defaultdict(int)
    sections: dict[str, list[str]] = defaultdict(list)
    for a in alerts:
        heading = _HEADINGS[a.kind]
        counts[heading] += len(a.keys) if a.kind == "api_error" else 1
        sections[heading].append(f"- {a.text}")
    summary = ", ".join(f"{heading.lower()} ({n})" for heading, n in counts.items())
    body = "\n\n".join(f"{heading}\n\n" + "\n".join(lines) for heading, lines in sections.items())

    message = EmailMessage()
    message["Subject"] = f"Engram alert: {summary}"
    message["From"] = settings.smtp_from or settings.alert_email
    message["To"] = settings.alert_email
    message.set_content(
        f"{body}\n\nEach alert is sent once. Engram checks every 15 minutes "
        f"({settings.environment}).\n"
    )
    return message


def send(settings: Settings, message: EmailMessage) -> None:
    assert settings.smtp_host is not None
    connect = smtplib.SMTP_SSL if settings.smtp_port == 465 else smtplib.SMTP
    with connect(settings.smtp_host, settings.smtp_port, timeout=30) as smtp:
        if connect is smtplib.SMTP and settings.smtp_starttls:
            smtp.starttls()
        if settings.smtp_username:
            smtp.login(settings.smtp_username, settings.smtp_password.get_secret_value())
        smtp.send_message(message)


Sender = Callable[[Settings, EmailMessage], None]


async def check(
    conn: AsyncConnection[Any],
    settings: Settings,
    *,
    now: datetime | None = None,
    sender: Sender = send,
) -> int:
    """Email every alert not yet sent and remember them. Returns how many alerts were sent."""
    now = now or datetime.now(UTC)
    await conn.execute("delete from public.api_errors where created_at < %s", (now - KEEP,))
    await conn.execute("delete from public.alerts_sent where sent_at < %s", (now - KEEP,))
    alerts = await collect(conn, settings, now)
    if not alerts:
        return 0
    if not (settings.alert_email and settings.smtp_host):
        logger.warning(
            "%s alerts, not sent (no alert email or SMTP host):\n%s",
            len(alerts),
            "\n".join(a.text for a in alerts),
        )
        return 0
    await asyncio.to_thread(sender, settings, compose(alerts, settings))
    # Remembered only once the email is out, so a failed send is tried again next time.
    async with conn.cursor() as cur:
        await cur.executemany(
            "insert into public.alerts_sent (kind, key) values (%s, %s) on conflict do nothing",
            [(a.kind, key) for a in alerts for key in a.keys],
        )
    logger.info("sent %s alerts", len(alerts))
    return len(alerts)


async def run(settings: Settings) -> int:
    async with await AsyncConnection.connect(settings.database_url, autocommit=True) as conn:
        return await check(conn, settings)


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    sent = asyncio.run(run(get_settings()))
    print(f"{sent} alerts sent")


if __name__ == "__main__":
    main()
