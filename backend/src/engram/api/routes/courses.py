"""Courses as students see them: each textbook's chapters, and which have been covered.

Marking a chapter covered is the only trigger for card generation (D4). Coverage is stored
per section; students mark chapters, which `chapters` picks out of the parsed sections.
"""

import re
from collections import defaultdict
from datetime import datetime
from uuid import UUID

import psycopg
from fastapi import APIRouter, HTTPException, Response, status
from psycopg.rows import class_row
from pydantic import BaseModel

from engram.api.db import UserDb

router = APIRouter()


class Chapter(BaseModel):
    id: UUID
    title: str
    page_start: int | None
    page_end: int | None
    covered_at: datetime | None


class Textbook(BaseModel):
    material_id: UUID
    title: str
    chapters: list[Chapter]


class Material(BaseModel):
    id: UUID
    title: str
    kind: str
    status: str


class Course(BaseModel):
    id: UUID
    title: str
    textbooks: list[Textbook]
    materials: list[Material]


class CourseSummary(BaseModel):
    id: UUID
    title: str
    chapters: int
    covered: int


class Coverage(BaseModel):
    section_id: UUID
    covered_at: datetime


class _SectionRow(BaseModel):
    id: UUID
    material_id: UUID
    level: int
    title: str
    page_start: int | None
    page_end: int | None
    covered_at: datetime | None


_CHAPTER = re.compile(r"^chapter\s+(\w+)", re.IGNORECASE)
# Front and back matter: in the table of contents, but nothing to study or make cards from.
_MATTER = re.compile(
    r"^(contents|table of contents|preface|foreword|acknowledg\w*|about\b.*|index"
    r"|references|bibliography|glossary|answer key|credits|appendix\b.*)$",
    re.IGNORECASE,
)


def _is_numbered_chapter(title: str) -> bool:
    """`Chapter 3 ...` or `Chapter IV ...`, but not `Chapter Outline` or `Chapter Summary`."""
    match = _CHAPTER.match(title.strip())
    if match is None:
        return False
    return match[1].isdigit() or re.fullmatch(r"[IVXLC]+", match[1]) is not None


def chapters[S: _SectionRow](sections: list[S]) -> list[S]:
    """The sections a student marks covered. Sections titled `Chapter N` wherever they sit
    (some books group chapters into units); otherwise the top level, minus front and back
    matter."""
    numbered = [s for s in sections if _is_numbered_chapter(s.title)]
    if numbered:
        return numbered
    return [s for s in sections if s.level == 1 and not _MATTER.match(s.title.strip())]


_SECTIONS = """
select s.id, s.material_id, s.level, s.title, s.page_start, s.page_end, c.covered_at
  from public.sections s
  join public.materials m on m.id = s.material_id
  left join public.covered_sections c on c.section_id = s.id
 where m.kind = 'textbook' and m.status = 'ready' and m.course_id = any(%s)
 order by m.created_at, s.ordinal
"""


async def _chapters_by_material(db: UserDb, course_ids: list[UUID]) -> dict[UUID, list[Chapter]]:
    async with db.cursor(row_factory=class_row(_SectionRow)) as cur:
        await cur.execute(_SECTIONS, (course_ids,))
        rows = await cur.fetchall()
    by_material: dict[UUID, list[_SectionRow]] = defaultdict(list)
    for row in rows:
        by_material[row.material_id].append(row)
    return {
        material: [Chapter.model_validate(s, from_attributes=True) for s in chapters(sections)]
        for material, sections in by_material.items()
    }


@router.get("/courses")
async def list_courses(db: UserDb) -> list[CourseSummary]:
    cur = await db.execute(
        "select c.id, c.title, array_remove(array_agg(m.id), null)"
        " from public.courses c"
        " left join public.materials m"
        "   on m.course_id = c.id and m.kind = 'textbook' and m.status = 'ready'"
        " group by c.id order by c.title"
    )
    courses = await cur.fetchall()
    by_material = await _chapters_by_material(db, [c[0] for c in courses])
    summaries = []
    for course_id, title, material_ids in courses:
        found = [ch for m in material_ids for ch in by_material.get(m, [])]
        covered = sum(ch.covered_at is not None for ch in found)
        summaries.append(
            CourseSummary(id=course_id, title=title, chapters=len(found), covered=covered)
        )
    return summaries


@router.get("/courses/{course_id}")
async def get_course(course_id: UUID, db: UserDb) -> Course:
    cur = await db.execute("select title from public.courses where id = %s", (course_id,))
    row = await cur.fetchone()
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Course not found")

    async with db.cursor(row_factory=class_row(Material)) as mcur:
        await mcur.execute(
            "select id, title, kind::text as kind, status::text as status"
            " from public.materials where course_id = %s order by created_at",
            (course_id,),
        )
        materials = await mcur.fetchall()

    by_material = await _chapters_by_material(db, [course_id])
    textbooks = [
        Textbook(material_id=m.id, title=m.title, chapters=by_material[m.id])
        for m in materials
        if m.id in by_material
    ]
    return Course(id=course_id, title=row[0], textbooks=textbooks, materials=materials)


@router.put("/sections/{section_id}/covered")
async def mark_covered(section_id: UUID, db: UserDb) -> Coverage:
    try:
        await db.execute(
            "insert into public.covered_sections (section_id) values (%s)"
            " on conflict (section_id) do nothing",
            (section_id,),
        )
    except (psycopg.errors.InsufficientPrivilege, psycopg.errors.ForeignKeyViolation):
        # Someone else's section, or none at all: the same answer for both.
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Section not found") from None
    cur = await db.execute(
        "select covered_at from public.covered_sections where section_id = %s", (section_id,)
    )
    row = await cur.fetchone()
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Section not found")
    return Coverage(section_id=section_id, covered_at=row[0])


@router.delete("/sections/{section_id}/covered", status_code=status.HTTP_204_NO_CONTENT)
async def unmark_covered(section_id: UUID, db: UserDb) -> Response:
    await db.execute("delete from public.covered_sections where section_id = %s", (section_id,))
    return Response(status_code=status.HTTP_204_NO_CONTENT)
