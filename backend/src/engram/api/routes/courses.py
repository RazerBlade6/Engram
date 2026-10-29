"""Courses as students see them: each textbook's chapters, and which have been covered.

Marking a chapter covered is the only trigger for card generation (D4): a database trigger
queues the job (see the cards migration). Coverage is stored per section; students mark
chapters, which `chapters` picks out of the parsed sections.
"""

import logging
import re
from collections import defaultdict
from datetime import datetime
from uuid import UUID

import psycopg
from fastapi import APIRouter, HTTPException, Response, status
from psycopg.rows import class_row
from pydantic import BaseModel, Field

from engram.api import usage
from engram.api.db import UserDb
from engram.api.files import Files
from engram.api.usage import Visit

logger = logging.getLogger(__name__)

router = APIRouter()


class Chapter(BaseModel):
    id: UUID
    title: str
    page_start: int | None
    page_end: int | None
    covered_at: datetime | None
    # Kept when a chapter is unmarked, so an unmarked chapter can still have cards.
    cards: int
    # While covered: 'pending' until its cards are made, then 'ready' or 'failed'.
    cards_status: str | None
    # While pending: cards drafted so far, before repeats are dropped (D53).
    cards_drafted: int


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
    owner_id: UUID
    title: str
    chapters: int
    covered: int


class NewCourse(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    # Admins create courses for someone else; students only for themselves (row-level security).
    owner_id: UUID | None = None


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
    cards: int
    cards_status: str | None
    cards_drafted: int


class Source(BaseModel):
    quote: str
    heading_path: list[str]
    page: int | None


class Card(BaseModel):
    id: UUID
    kind: str
    concept: str
    prompt: str
    answer: str
    choices: list[str]
    sources: list[Source]


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
select s.id, s.material_id, s.level, s.title, s.page_start, s.page_end, c.covered_at,
       (select count(*) from public.cards k where k.section_id = s.id)::int as cards,
       c.cards_status::text as cards_status,
       coalesce(c.cards_drafted, 0) as cards_drafted
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
        "select c.id, c.owner_id, c.title, array_remove(array_agg(m.id), null)"
        " from public.courses c"
        " left join public.materials m"
        "   on m.course_id = c.id and m.kind = 'textbook' and m.status = 'ready'"
        " group by c.id order by c.title"
    )
    courses = await cur.fetchall()
    by_material = await _chapters_by_material(db, [c[0] for c in courses])
    summaries = []
    for course_id, owner_id, title, material_ids in courses:
        found = [ch for m in material_ids for ch in by_material.get(m, [])]
        covered = sum(ch.covered_at is not None for ch in found)
        summaries.append(
            CourseSummary(
                id=course_id, owner_id=owner_id, title=title, chapters=len(found), covered=covered
            )
        )
    return summaries


@router.post("/courses", status_code=status.HTTP_201_CREATED)
async def create_course(body: NewCourse, db: UserDb, visit: Visit) -> CourseSummary:
    title = body.title.strip()
    if not title:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "A course needs a name")
    try:
        cur = await db.execute(
            "insert into public.courses (owner_id, title)"
            " values (coalesce(%s, (select auth.uid())), %s) returning id, owner_id",
            (body.owner_id, title),
        )
    except psycopg.errors.InsufficientPrivilege:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Admins only") from None
    except psycopg.errors.ForeignKeyViolation:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No such person") from None
    row = await cur.fetchone()
    assert row is not None
    await usage.log(db, visit, "course_created", course_id=row[0])
    return CourseSummary(id=row[0], owner_id=row[1], title=title, chapters=0, covered=0)


@router.delete("/courses/{course_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_course(course_id: UUID, db: UserDb, storage: Files, visit: Visit) -> Response:
    """Admins only (row-level security). Its materials, chapters, cards, reviews, coverage and
    dates go with it by cascade; usage events that mention it are kept."""
    cur = await db.execute(
        "select storage_path from public.materials where course_id = %s", (course_id,)
    )
    paths = [row[0] for row in await cur.fetchall()]
    cur = await db.execute("delete from public.courses where id = %s", (course_id,))
    if not cur.rowcount:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Course not found")
    await usage.log(db, visit, "course_deleted", course_id=course_id)
    for path in paths:
        try:
            await storage.remove_material(path)
        except Exception:
            # The course is gone; leftover files are only a storage cost.
            logger.exception("could not remove the stored files at %s", path)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


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
async def mark_covered(section_id: UUID, db: UserDb, visit: Visit) -> Coverage:
    try:
        inserted = await db.execute(
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
    if inserted.rowcount:
        await usage.log(db, visit, "chapter_covered", section_id=section_id)
    return Coverage(section_id=section_id, covered_at=row[0])


@router.get("/sections/{section_id}/cards")
async def list_cards(section_id: UUID, db: UserDb) -> list[Card]:
    cur = await db.execute("select 1 from public.sections where id = %s", (section_id,))
    if await cur.fetchone() is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Section not found")
    cur = await db.execute(
        "select id, kind::text, concept, prompt, answer, choices, sources from public.cards"
        " where section_id = %s order by ordinal",
        (section_id,),
    )
    return [
        Card(
            id=id,
            kind=kind,
            concept=concept,
            prompt=prompt,
            answer=answer,
            choices=choices,
            sources=[
                Source(
                    quote=src["quote"],
                    heading_path=src["heading_path"],
                    page=src["locations"][0]["page"] if src["locations"] else None,
                )
                for src in sources
            ],
        )
        for id, kind, concept, prompt, answer, choices, sources in await cur.fetchall()
    ]


@router.delete("/sections/{section_id}/covered", status_code=status.HTTP_204_NO_CONTENT)
async def unmark_covered(section_id: UUID, db: UserDb, visit: Visit) -> Response:
    cur = await db.execute(
        "delete from public.covered_sections where section_id = %s", (section_id,)
    )
    if cur.rowcount:
        await usage.log(db, visit, "chapter_unmarked", section_id=section_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
