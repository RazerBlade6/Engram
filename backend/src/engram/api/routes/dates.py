"""Important dates per course (exams, quizzes and deadlines) for the calendar and Today.

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

from engram.api.db import UserDb

router = APIRouter()

Kind = Literal["exam", "quiz", "deadline"]
# Wide enough for any course, narrow enough to catch a mistyped year.
Day = Annotated[date, Field(ge=date(2000, 1, 1), le=date(2100, 12, 31))]
Title = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]


class NewDate(BaseModel):
    kind: Kind
    title: Title
    on: Day


class CourseDate(BaseModel):
    id: UUID
    course_id: UUID
    course: str
    kind: Kind
    title: str
    on: date


_SELECT = """
select d.id, d.course_id, c.title as course, d.kind::text as kind, d.title, d.on_date as on
  from public.course_dates d
  join public.courses c on c.id = d.course_id
"""


async def _one(db: UserDb, date_id: UUID) -> CourseDate:
    async with db.cursor(row_factory=class_row(CourseDate)) as cur:
        await cur.execute(_SELECT + " where d.id = %s", (date_id,))
        found = await cur.fetchone()
    if found is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Date not found")
    return found


@router.get("/dates")
async def list_dates(db: UserDb) -> list[CourseDate]:
    """Every date across the student's courses, earliest first."""
    async with db.cursor(row_factory=class_row(CourseDate)) as cur:
        await cur.execute(_SELECT + " order by d.on_date, c.title, d.created_at")
        return await cur.fetchall()


@router.post("/courses/{course_id}/dates", status_code=status.HTTP_201_CREATED)
async def add_date(course_id: UUID, body: NewDate, db: UserDb) -> CourseDate:
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
    return await _one(db, row[0])


@router.put("/dates/{date_id}")
async def change_date(date_id: UUID, body: NewDate, db: UserDb) -> CourseDate:
    cur = await db.execute(
        "update public.course_dates set kind = %s, title = %s, on_date = %s where id = %s",
        (body.kind, body.title, body.on, date_id),
    )
    if cur.rowcount == 0:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Date not found")
    return await _one(db, date_id)


@router.delete("/dates/{date_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_date(date_id: UUID, db: UserDb) -> Response:
    await db.execute("delete from public.course_dates where id = %s", (date_id,))
    return Response(status_code=status.HTTP_204_NO_CONTENT)
