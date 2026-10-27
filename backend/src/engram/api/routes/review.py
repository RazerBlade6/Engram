"""Reviewing cards: what's due, rating a card, and flagging one that's wrong.

The queue is cards due today plus a few new ones (see `engram.review`), from the courses the
student owns. Cards of a chapter that has since been unmarked stay in it. Rows are read and
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
from engram.api.db import UserDb
from engram.review import Day, Progress

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
    cards: list[ReviewCard]


class Summary(BaseModel):
    due: int
    new: int
    minutes: int
    courses: list[str]


class Rating(BaseModel):
    rating: int = Field(ge=1, le=4)


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
        # Chunks begin with their heading path, which the card already shows.
        prefix = " > ".join(row["chunk_heading_path"]) + "\n\n"
        passage = row["chunk"].removeprefix(prefix)
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


async def _queue(db: UserDb, day: Day) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    due = await _rows(
        db,
        _DUE,
        {"end": day.end, "ahead": day.now + scheduling.LEARN_AHEAD, "limit": QUEUE_LIMIT},
    )
    new = await _rows(db, _NEW, {"limit": await _new_allowance(db, day)})
    return due, new


@router.get("/review/queue")
async def queue(db: UserDb, day: Today) -> Queue:
    """Cards due today first, then today's new cards."""
    due, new = await _queue(db, day)
    return Queue(cards=[_card(row, day.now) for row in [*due, *new]])


@router.get("/review/summary")
async def summary(db: UserDb, day: Today) -> Summary:
    due, new = await _queue(db, day)
    count = len(due) + len(new)
    courses = list(dict.fromkeys(row["course"] for row in [*due, *new]))
    minutes = max(1, round(count * scheduling.SECONDS_PER_CARD / 60)) if count else 0
    return Summary(due=len(due), new=len(new), minutes=minutes, courses=courses)


async def _current(db: UserDb, card_id: UUID) -> dict[str, Any]:
    rows = await _rows(db, _CARD + " where k.id = %(id)s", {"id": card_id})
    if not rows:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Card not found")
    return rows[0]


@router.post("/cards/{card_id}/review")
async def rate(card_id: UUID, body: Rating, db: UserDb, day: Today) -> Reviewed:
    progress = _progress(await _current(db, card_id))
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
    return Reviewed(due=after.due, next=scheduling.preview(after, day.now))


@router.put("/cards/{card_id}/flag", status_code=status.HTTP_204_NO_CONTENT)
async def flag(card_id: UUID, body: Flag, db: UserDb, day: Today) -> Response:
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
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.delete("/cards/{card_id}/flag", status_code=status.HTTP_204_NO_CONTENT)
async def unflag(card_id: UUID, db: UserDb) -> Response:
    """Put a flagged card back into reviews, where it was."""
    await db.execute(
        "update public.card_progress set flag = null, flagged_at = null"
        " where card_id = %s and user_id = (select auth.uid())",
        (card_id,),
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)
