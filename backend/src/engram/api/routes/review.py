"""Reviewing cards: what's due, rating a card, and flagging one that's wrong.

The queue is cards due today plus a few new ones (see `engram.review`), from the courses the
student owns, arranged in the review order an admin set for them. Cards of a chapter that has
since been unmarked stay in it. Rows are read and
written as the student, so RLS keeps each student to their own progress.
"""

import re
from datetime import UTC, datetime
from typing import Annotated, Any, Literal
from uuid import UUID
from zoneinfo import ZoneInfo

import psycopg
from fastapi import APIRouter, Depends, Header, HTTPException, Response, status
from psycopg.rows import dict_row
from pydantic import BaseModel, Field

from engram import review as scheduling
from engram.api import usage
from engram.api.db import UserDb
from engram.api.usage import Visit
from engram.chat.retrieve import body
from engram.review import Day, Order, Progress, Session

router = APIRouter()

QUEUE_LIMIT = 500


def get_day(x_timezone: Annotated[str | None, Header()] = None) -> Day:
    """The student's day, from the time zone their browser reports."""
    tz: ZoneInfo = scheduling.timezone(x_timezone)
    return Day.of(datetime.now(UTC), tz)


Today = Annotated[Day, Depends(get_day)]


class Source(BaseModel):
    book: str
    heading_path: list[str]
    page: int | None
    # The passage the card comes from, and where the quoted words sit in it (if found).
    passage: str
    highlight: tuple[int, int] | None


class ReviewCard(BaseModel):
    id: UUID
    kind: str
    prompt: str
    answer: str
    choices: list[str]
    course: str
    chapter: str | None
    new: bool
    # When the card would next be due for each rating, 1 (forgot) to 4 (easy).
    next: dict[int, datetime]
    source: Source | None


class Queue(BaseModel):
    order: Order
    cards: list[ReviewCard]


class SessionSummary(BaseModel):
    session: Session
    cards: int
    minutes: int
    courses: list[str]


class Summary(BaseModel):
    order: Order
    # One entry, "review", unless the order is "separate": then "review" and "quiz".
    sessions: list[SessionSummary]


class Rating(BaseModel):
    rating: int = Field(ge=1, le=4)
    # From showing the card to rating it, for the usage log.
    ms: int | None = Field(default=None, ge=0, le=3_600_000)


class Reviewed(BaseModel):
    due: datetime
    next: dict[int, datetime]


class Flag(BaseModel):
    reason: Literal["wrong", "confusing", "not_useful"]


_CARD = """
select k.id, k.kind::text as kind, k.prompt, k.answer, k.choices, k.sources,
       c.title as course, s.title as chapter, m.title as book,
       ch.content as chunk, ch.heading_path as chunk_heading_path,
       p.state::text as state, p.step, p.stability, p.difficulty, p.due, p.last_review
  from public.cards k
  join public.materials m on m.id = k.material_id
  join public.courses c on c.id = m.course_id
  left join public.sections s on s.id = k.section_id
  left join public.chunks ch on ch.id = (k.sources -> 0 ->> 'chunk_id')::uuid
  left join public.card_progress p on p.card_id = k.id and p.user_id = (select auth.uid())
"""

_DUE = (
    _CARD
    + """
 where c.owner_id = (select auth.uid()) and p.flag is null
   and ((p.state = 'review' and p.due < %(end)s) or (p.state <> 'review' and p.due < %(ahead)s))
 order by p.due
 limit %(limit)s
"""
)

_NEW = (
    _CARD
    + """
  left join public.covered_sections cs on cs.section_id = k.section_id
 where c.owner_id = (select auth.uid()) and p.card_id is null
 order by cs.covered_at nulls last, m.created_at, s.ordinal, k.ordinal
 limit %(limit)s
"""
)


async def _new_allowance(db: UserDb, day: Day) -> int:
    cur = await db.execute(
        "select count(*) from public.card_progress"
        " where user_id = (select auth.uid()) and introduced_at >= %s"
        # Studied, not just flagged before it was ever shown.
        " and last_review is not null",
        (day.start,),
    )
    row = await cur.fetchone()
    return max(0, scheduling.NEW_PER_DAY - (row[0] if row else 0))


async def _rows(db: UserDb, sql: str, params: dict[str, Any]) -> list[dict[str, Any]]:
    async with db.cursor(row_factory=dict_row) as cur:
        await cur.execute(sql, params)
        return await cur.fetchall()


def _progress(row: dict[str, Any]) -> Progress | None:
    if row["state"] is None:
        return None
    return Progress(
        row["state"],
        row["step"],
        row["stability"],
        row["difficulty"],
        row["due"],
        row["last_review"],
    )


def highlight(passage: str, quote: str) -> tuple[int, int] | None:
    """Where `quote` sits in `passage`, allowing for differences in spacing and punctuation."""
    words = re.findall(r"\w+", quote)
    if not words:
        return None
    match = re.search(r"\W+".join(map(re.escape, words)), passage, re.IGNORECASE)
    return (match.start(), match.end()) if match else None


def _source(row: dict[str, Any]) -> Source | None:
    sources = row["sources"]
    if not sources:
        return None
    first = sources[0]
    passage = first["quote"]
    if row["chunk"]:
        passage = body(row["chunk"], row["chunk_heading_path"])
    locations = first.get("locations") or []
    return Source(
        book=row["book"],
        heading_path=first.get("heading_path") or [],
        page=locations[0]["page"] if locations else None,
        passage=passage,
        highlight=highlight(passage, first["quote"]),
    )


def _card(row: dict[str, Any], now: datetime) -> ReviewCard:
    progress = _progress(row)
    return ReviewCard(
        id=row["id"],
        kind=row["kind"],
        prompt=row["prompt"],
        answer=row["answer"],
        choices=row["choices"],
        course=row["course"],
        chapter=row["chapter"],
        new=progress is None,
        next=scheduling.preview(progress, now),
        source=_source(row),
    )


async def _order(db: UserDb) -> Order:
    cur = await db.execute(
        "select review_order::text from public.profiles where id = (select auth.uid())"
    )
    row = await cur.fetchone()
    return row[0] if row else "mixed"


async def _today(db: UserDb, day: Day) -> list[dict[str, Any]]:
    """Cards due today first, then today's new cards."""
    due = await _rows(
        db,
        _DUE,
        {"end": day.end, "ahead": day.now + scheduling.LEARN_AHEAD, "limit": QUEUE_LIMIT},
    )
    new = await _rows(db, _NEW, {"limit": await _new_allowance(db, day)})
    return [*due, *new]


def _kind(row: dict[str, Any]) -> str:
    return str(row["kind"])


@router.get("/review/queue")
async def queue(db: UserDb, day: Today, session: Session = "review") -> Queue:
    order = await _order(db)
    rows = scheduling.arrange(await _today(db, day), _kind, order, session)
    return Queue(order=order, cards=[_card(row, day.now) for row in rows])


@router.get("/review/summary")
async def summary(db: UserDb, day: Today) -> Summary:
    order = await _order(db)
    today = await _today(db, day)
    sessions = []
    for session in scheduling.sessions(order):
        rows = scheduling.arrange(today, _kind, order, session)
        count = len(rows)
        minutes = max(1, round(count * scheduling.SECONDS_PER_CARD / 60)) if count else 0
        courses = list(dict.fromkeys(row["course"] for row in rows))
        sessions.append(
            SessionSummary(session=session, cards=count, minutes=minutes, courses=courses)
        )
    return Summary(order=order, sessions=sessions)


async def _current(db: UserDb, card_id: UUID) -> dict[str, Any]:
    rows = await _rows(db, _CARD + " where k.id = %(id)s", {"id": card_id})
    if not rows:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Card not found")
    return rows[0]


@router.post("/cards/{card_id}/review")
async def rate(card_id: UUID, body: Rating, db: UserDb, day: Today, visit: Visit) -> Reviewed:
    row = await _current(db, card_id)
    progress = _progress(row)
    after = scheduling.review(progress, body.rating, day.now)
    try:
        await db.execute(
            "insert into public.card_progress"
            " (card_id, state, step, stability, difficulty, due, last_review)"
            " values (%s, %s, %s, %s, %s, %s, %s)"
            " on conflict (card_id, user_id) do update set state = excluded.state,"
            " step = excluded.step, stability = excluded.stability,"
            " difficulty = excluded.difficulty, due = excluded.due,"
            " last_review = excluded.last_review",
            (
                card_id,
                after.state,
                after.step,
                after.stability,
                after.difficulty,
                after.due,
                after.last_review,
            ),
        )
    except psycopg.errors.InsufficientPrivilege:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Card not found") from None
    await usage.log(db, visit, "review", **_review_event(card_id, row, body, progress, after, day))
    return Reviewed(due=after.due, next=scheduling.preview(after, day.now))


def _days(later: datetime, earlier: datetime) -> float:
    return round((later - earlier).total_seconds() / 86_400, 4)


def _review_event(
    card_id: UUID,
    row: dict[str, Any],
    body: Rating,
    before: Progress | None,
    after: Progress,
    day: Day,
) -> dict[str, Any]:
    """What a review log needs to evaluate or fit the scheduler later: the state before and
    after, the rating, and the time since the card was last seen."""
    last = before.last_review if before else None
    return {
        "card_id": card_id,
        "kind": row["kind"],
        "rating": body.rating,
        "ms": body.ms,
        "state_before": before.state if before else "new",
        "stability_before": before.stability if before else None,
        "difficulty_before": before.difficulty if before else None,
        "elapsed_days": _days(day.now, last) if last else None,
        "state_after": after.state,
        "stability_after": after.stability,
        "difficulty_after": after.difficulty,
        "scheduled_days": _days(after.due, day.now),
    }


@router.put("/cards/{card_id}/flag", status_code=status.HTTP_204_NO_CONTENT)
async def flag(card_id: UUID, body: Flag, db: UserDb, day: Today, visit: Visit) -> Response:
    """Take the card out of the student's reviews, noting why."""
    await _current(db, card_id)
    try:
        # A new card is flagged before it's ever been studied: it starts out suspended.
        await db.execute(
            "insert into public.card_progress (card_id, state, due, flag, flagged_at)"
            " values (%s, 'learning', %s, %s, %s)"
            " on conflict (card_id, user_id) do update"
            " set flag = excluded.flag, flagged_at = excluded.flagged_at",
            (card_id, day.now, body.reason, day.now),
        )
    except psycopg.errors.InsufficientPrivilege:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Card not found") from None
    await usage.log(db, visit, "flag", card_id=card_id, reason=body.reason)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.delete("/cards/{card_id}/flag", status_code=status.HTTP_204_NO_CONTENT)
async def unflag(card_id: UUID, db: UserDb, visit: Visit) -> Response:
    """Put a flagged card back into reviews, where it was."""
    cur = await db.execute(
        "update public.card_progress set flag = null, flagged_at = null"
        " where card_id = %s and user_id = (select auth.uid()) and flag is not null",
        (card_id,),
    )
    if cur.rowcount:
        await usage.log(db, visit, "unflag", card_id=card_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
