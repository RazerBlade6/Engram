"""The ingestion inspector (admin): what was extracted from each page of a material, and
where, so bad parses can be caught before students see them.

Boxes are [left, top, right, bottom] in PDF points from the page's top-left corner; the page
endpoint returns the page size in the same unit so the client can scale them onto the image.
"""

from datetime import datetime
from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from psycopg import AsyncConnection
from psycopg.rows import class_row
from pydantic import BaseModel

from engram.api.db import UserDb
from engram.api.pages import PageNotFound, PdfPages
from engram.api.routes.admin import require_admin

router = APIRouter(prefix="/admin/materials", dependencies=[Depends(require_admin)])


def get_pages(request: Request) -> PdfPages:
    pages: PdfPages = request.app.state.pages
    return pages


Pages = Annotated[PdfPages, Depends(get_pages)]


class MaterialSummary(BaseModel):
    id: UUID
    title: str
    kind: str
    status: str
    error: str | None
    page_count: int | None
    course: str
    created_at: datetime
    sections: int
    figures: int
    chunks: int


class Section(BaseModel):
    id: UUID
    parent_id: UUID | None
    ordinal: int
    level: int
    title: str
    page_start: int | None
    page_end: int | None


class PageStats(BaseModel):
    page: int
    text: int
    tables: int
    figures: int


class Inspection(BaseModel):
    material: MaterialSummary
    # False for PowerPoint files: their pages can be listed but not rendered.
    preview: bool
    sections: list[Section]
    pages: list[PageStats]  # only pages with extracted content


class ChunkBox(BaseModel):
    chunk_id: UUID
    ordinal: int
    kind: str
    heading_path: list[str]
    content: str
    bbox: list[float]
    part: int  # this box's position among the chunk's boxes, 1-based
    parts: int


class FigureBox(BaseModel):
    id: UUID
    ordinal: int
    bbox: list[float]
    caption: str | None
    description: str | None
    labels: list[str]
    described_by: str | None


class Page(BaseModel):
    page: int
    width: float | None
    height: float | None
    chunks: list[ChunkBox]
    figures: list[FigureBox]


_SUMMARY = """
select m.id, m.title, m.kind::text as kind, m.status::text as status, m.error, m.page_count,
       c.title as course, m.created_at,
       (select count(*) from public.sections s where s.material_id = m.id) as sections,
       (select count(*) from public.figures f where f.material_id = m.id) as figures,
       (select count(*) from public.chunks k where k.material_id = m.id) as chunks
  from public.materials m
  join public.courses c on c.id = m.course_id
"""


@router.get("")
async def list_materials(db: UserDb) -> list[MaterialSummary]:
    async with db.cursor(row_factory=class_row(MaterialSummary)) as cur:
        await cur.execute(_SUMMARY + " order by m.created_at desc")
        return await cur.fetchall()


@router.get("/{material_id}")
async def inspect(material_id: UUID, db: UserDb) -> Inspection:
    async with db.cursor(row_factory=class_row(MaterialSummary)) as cur:
        await cur.execute(_SUMMARY + " where m.id = %s", (material_id,))
        material = await cur.fetchone()
    if material is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Material not found")
    storage_path = await _storage_path(db, material_id)

    async with db.cursor(row_factory=class_row(Section)) as cur:
        await cur.execute(
            "select id, parent_id, ordinal, level, title, page_start, page_end"
            " from public.sections where material_id = %s order by ordinal",
            (material_id,),
        )
        sections = await cur.fetchall()

    async with db.cursor(row_factory=class_row(PageStats)) as cur:
        await cur.execute(
            "select (loc->>'page')::int as page,"
            " count(*) filter (where kind in ('text', 'slide')) as text,"
            " count(*) filter (where kind = 'table') as tables,"
            " count(*) filter (where kind = 'figure') as figures"
            " from public.chunks, jsonb_array_elements(locations) as loc"
            " where material_id = %s group by 1 order by 1",
            (material_id,),
        )
        pages = await cur.fetchall()

    return Inspection(
        material=material, preview=_is_pdf(storage_path), sections=sections, pages=pages
    )


@router.get("/{material_id}/pages/{page}")
async def page_contents(material_id: UUID, page: int, db: UserDb, pdf: Pages) -> Page:
    storage_path = await _storage_path(db, material_id)

    async with db.cursor(row_factory=class_row(ChunkBox)) as cur:
        # Figures have their own boxes below; their chunks would only draw the same box twice.
        await cur.execute(
            "select k.id as chunk_id, k.ordinal, k.kind::text as kind, k.heading_path,"
            " k.content, array(select jsonb_array_elements_text(loc.value->'bbox'))::float8[]"
            " as bbox, loc.ordinality::int as part, jsonb_array_length(k.locations) as parts"
            " from public.chunks k, jsonb_array_elements(k.locations) with ordinality as loc"
            " where k.material_id = %s and k.kind <> 'figure'"
            " and (loc.value->>'page')::int = %s"
            " order by k.ordinal, loc.ordinality",
            (material_id, page),
        )
        chunks = await cur.fetchall()

    async with db.cursor(row_factory=class_row(FigureBox)) as cur:
        await cur.execute(
            "select id, ordinal, bbox, caption, description, labels, described_by"
            " from public.figures where material_id = %s and page = %s order by ordinal",
            (material_id, page),
        )
        figures = await cur.fetchall()

    width = height = None
    if _is_pdf(storage_path):
        try:
            width, height = await pdf.size(storage_path, page)
        except PageNotFound:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "No such page") from None
    return Page(page=page, width=width, height=height, chunks=chunks, figures=figures)


@router.get(
    "/{material_id}/pages/{page}/image",
    response_class=Response,
    responses={200: {"content": {"image/jpeg": {}}}},
)
async def page_image(material_id: UUID, page: int, db: UserDb, pdf: Pages) -> Response:
    storage_path = await _storage_path(db, material_id)
    if not _is_pdf(storage_path):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Only PDF pages can be rendered")
    try:
        image = await pdf.render(storage_path, page)
    except PageNotFound:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No such page") from None
    return Response(
        image, media_type="image/jpeg", headers={"Cache-Control": "private, max-age=3600"}
    )


async def _storage_path(db: AsyncConnection[Any], material_id: UUID) -> str:
    cur = await db.execute(
        "select storage_path from public.materials where id = %s", (material_id,)
    )
    row = await cur.fetchone()
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Material not found")
    path: str = row[0]
    return path


def _is_pdf(storage_path: str) -> bool:
    return storage_path.lower().endswith(".pdf")
