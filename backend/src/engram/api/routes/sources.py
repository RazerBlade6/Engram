"""The source viewer: the page a citation points to, with the cited passage boxed.

Boxes are [left, top, right, bottom] in PDF points from the page's top-left corner, and the
page size is in the same unit, so the client can scale them onto the page image. Materials
that aren't PDFs (PowerPoint uploads) have no page image; the viewer shows the passage text.
"""

from uuid import UUID

from fastapi import APIRouter, HTTPException, Response, status
from psycopg.rows import dict_row
from pydantic import BaseModel

from engram.api.db import UserDb
from engram.api.pages import PageNotFound
from engram.api.routes.inspector import Pages, is_pdf, page_jpeg
from engram.chat.retrieve import body

router = APIRouter()


class Box(BaseModel):
    page: int
    bbox: list[float]


class SourcePage(BaseModel):
    chunk_id: UUID
    material_id: UUID
    book: str
    heading_path: list[str]
    passage: str
    # The first page the passage is on, with its size when there's an image of it.
    page: int | None
    width: float | None
    height: float | None
    boxes: list[Box]


@router.get("/chunks/{chunk_id}/source")
async def source(chunk_id: UUID, db: UserDb, pdf: Pages) -> SourcePage:
    async with db.cursor(row_factory=dict_row) as cur:
        await cur.execute(
            "select k.material_id, m.title as book, m.storage_path, k.heading_path, k.content,"
            " k.locations from public.chunks k join public.materials m on m.id = k.material_id"
            " where k.id = %s",
            (chunk_id,),
        )
        row = await cur.fetchone()
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Source not found")
    boxes = [Box(page=loc["page"], bbox=loc["bbox"]) for loc in row["locations"]]
    page = boxes[0].page if boxes else None
    width = height = None
    if page is not None and is_pdf(row["storage_path"]):
        try:
            width, height = await pdf.size(row["storage_path"], page)
        except PageNotFound:
            page = None
    return SourcePage(
        chunk_id=chunk_id,
        material_id=row["material_id"],
        book=row["book"],
        heading_path=row["heading_path"],
        passage=body(row["content"], row["heading_path"]),
        page=page,
        width=width,
        height=height,
        boxes=boxes,
    )


@router.get(
    "/materials/{material_id}/pages/{page}/image",
    response_class=Response,
    responses={200: {"content": {"image/jpeg": {}}}},
)
async def page_image(material_id: UUID, page: int, db: UserDb, pdf: Pages) -> Response:
    return await page_jpeg(db, pdf, material_id, page)
