"""Important dates per course (exams, quizzes and deadlines) for the calendar and Today.

A date can say which chapters it covers. That's optional, and used by focus mode (Phase 3)
to prioritize those chapters ahead of an exam.

Dates are calendar days with no time or time zone: "upcoming" is worked out by the browser,
in the student's own today.
"""

from datetime import date
from typing import Annotated, Literal
from uuid import UUID

import psycopg
from fastapi import APIRouter, HTTPException, Response, status
from psycopg.rows import class_row
from pydantic import BaseModel, Field, StringConstraints

from engram.api import usage
from engram.api.db import UserDb
from engram.api.usage import Visit

router = APIRouter()

Kind = Literal["exam", "quiz", "deadline"]
# Wide enough for any course, narrow enough to catch a mistyped year.
Day = Annotated[date, Field(ge=date(2000, 1, 1), le=date(2100, 12, 31))]
Title = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]


class NewDate(BaseModel):
    kind: Kind
    title: Title
    on: Day
    # Section ids of the chapters it covers, from the date's own course.
    chapters: Annotated[list[UUID], Field(max_length=200)] = []


class DateChapter(BaseModel):
    id: UUID
    title: str


class CourseDate(BaseModel):
    id: UUID
    course_id: UUID
    course: str
    kind: Kind
    title: str
    on: date
    # In book order.
    chapters: list[DateChapter]


_SELECT = """
select d.id, d.course_id, c.title as course, d.kind::text as kind, d.title, d.on_date as on,
       coalesce((
         select jsonb_agg(jsonb_build_object('id', s.id, 'title', s.title)
                          order by m.created_at, s.ordinal)
           from public.course_date_chapters dc
           join public.sections s on s.id = dc.section_id
           join public.materials m on m.id = s.material_id
          where dc.date_id = d.id
       ), '[]') as chapters
  from public.course_dates d
  join public.courses c on c.id = d.course_id
"""


async def _set_chapters(db: UserDb, date_id: UUID, chapters: list[UUID]) -> None:
    await db.execute("delete from public.course_date_chapters where date_id = %s", (date_id,))
    if not chapters:
        return
    try:
        await db.execute(
            "insert into public.course_date_chapters (date_id, section_id)"
            " select %s, unnest(%s::uuid[]) on conflict do nothing",
            (date_id, chapters),
        )
    except (psycopg.errors.InsufficientPrivilege, psycopg.errors.ForeignKeyViolation):
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT, "Chapters must be from the date's course"
        ) from None


async def _one(db: UserDb, date_id: UUID) -> CourseDate:
    async with db.cursor(row_factory=class_row(CourseDate)) as cur:
        await cur.execute(_SELECT + " where d.id = %s", (date_id,))
        found = await cur.fetchone()
    if found is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Date not found")
    return found


def _described(body: NewDate) -> dict[str, object]:
    """A date for the usage log: its kind and how many chapters, not its name."""
    return {"kind": body.kind, "on": body.on, "chapters": len(body.chapters)}


@router.get("/dates")
async def list_dates(db: UserDb) -> list[CourseDate]:
    """Every date across the student's courses, earliest first."""
    async with db.cursor(row_factory=class_row(CourseDate)) as cur:
        await cur.execute(_SELECT + " order by d.on_date, c.title, d.created_at")
        return await cur.fetchall()


@router.post("/courses/{course_id}/dates", status_code=status.HTTP_201_CREATED)
async def add_date(course_id: UUID, body: NewDate, db: UserDb, visit: Visit) -> CourseDate:
    try:
        cur = await db.execute(
            "insert into public.course_dates (course_id, kind, title, on_date)"
            " values (%s, %s, %s, %s) returning id",
            (course_id, body.kind, body.title, body.on),
        )
    except (psycopg.errors.InsufficientPrivilege, psycopg.errors.ForeignKeyViolation):
        # Someone else's course, or none at all: the same answer for both.
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Course not found") from None
    row = await cur.fetchone()
    assert row is not None
    await _set_chapters(db, row[0], body.chapters)
    await usage.log(db, visit, "date_added", date_id=row[0], **_described(body))
    return await _one(db, row[0])


@router.put("/dates/{date_id}")
async def change_date(date_id: UUID, body: NewDate, db: UserDb, visit: Visit) -> CourseDate:
    cur = await db.execute(
        "update public.course_dates set kind = %s, title = %s, on_date = %s where id = %s",
        (body.kind, body.title, body.on, date_id),
    )
    if cur.rowcount == 0:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Date not found")
    await _set_chapters(db, date_id, body.chapters)
    await usage.log(db, visit, "date_changed", date_id=date_id, **_described(body))
    return await _one(db, date_id)


@router.delete("/dates/{date_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_date(date_id: UUID, db: UserDb, visit: Visit) -> Response:
    cur = await db.execute("delete from public.course_dates where id = %s", (date_id,))
    if cur.rowcount:
        await usage.log(db, visit, "date_deleted", date_id=date_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
