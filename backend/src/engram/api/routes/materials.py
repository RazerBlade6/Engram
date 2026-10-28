"""Adding materials to a course, and removing them. Students add slides; admins also add
textbooks (the materials insert policy enforces both).

The browser uploads the file straight to Storage, because Cloud Run caps request bodies at
32 MiB. Adding takes three steps:

1. `POST /courses/{id}/materials` records the material as 'uploading' and returns a token
   for uploading the file to its storage path.
2. The browser uploads the file with that token.
3. `POST /materials/{id}/queue` checks the stored file and queues it for ingestion (via
   `queue_material`). A file that isn't a PDF or PowerPoint is removed along with its material.
"""

import logging
from pathlib import Path
from typing import Annotated, Literal
from uuid import UUID, uuid4

import psycopg
from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from engram.api import usage
from engram.api.db import UserDb
from engram.api.routes.courses import Material
from engram.api.usage import Visit
from engram.storage import Storage, safe_filename

logger = logging.getLogger(__name__)

router = APIRouter()

MB = 2**20
# Generous for lecture slides; textbooks are bounded by the bucket's own limit.
MAX_UPLOAD_BYTES = {"slides": 100 * MB, "textbook": 500 * MB}

PDF = "application/pdf"
PPTX = "application/vnd.openxmlformats-officedocument.presentationml.presentation"
CONTENT_TYPES = {".pdf": PDF, ".pptx": PPTX}

UNSUPPORTED = "Engram can read PDF and PowerPoint (.pptx) files."


def get_storage(request: Request) -> Storage:
    storage: Storage = request.app.state.storage
    return storage


Files = Annotated[Storage, Depends(get_storage)]


class NewMaterial(BaseModel):
    filename: str = Field(min_length=1, max_length=255)
    size: int = Field(ge=0)
    kind: Literal["slides", "textbook"] = "slides"


class Upload(BaseModel):
    # Upload with PUT to <supabase>/storage/v1/object/upload/sign/materials/<path>?token=<token>.
    path: str
    token: str


class PendingMaterial(BaseModel):
    material: Material
    upload: Upload


def detect_type(head: bytes, suffix: str) -> str | None:
    """PDF or PowerPoint, judged by the file's first bytes. A .pptx is a zip archive; one that
    isn't a presentation fails at ingestion and shows as unreadable."""
    if head.startswith(b"%PDF-"):
        return PDF
    if head.startswith(b"PK") and suffix == ".pptx":
        return PPTX
    return None


def title_from(filename: str) -> str:
    return Path(filename).stem.replace("_", " ").strip()[:200] or "Slides"


@router.post("/courses/{course_id}/materials", status_code=status.HTTP_201_CREATED)
async def add(course_id: UUID, body: NewMaterial, db: UserDb, storage: Files) -> PendingMaterial:
    cur = await db.execute("select 1 from public.courses where id = %s", (course_id,))
    if await cur.fetchone() is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Course not found")

    suffix = Path(body.filename).suffix.lower()
    if suffix not in CONTENT_TYPES:
        raise HTTPException(status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, UNSUPPORTED)
    limit = MAX_UPLOAD_BYTES[body.kind]
    if body.size > limit:
        raise HTTPException(
            status.HTTP_413_CONTENT_TOO_LARGE, f"That file is over {limit // MB} MB."
        )

    material_id = uuid4()
    path = f"{course_id}/{material_id}/{safe_filename(body.filename)}"
    title = title_from(body.filename)
    try:
        await db.execute(
            "insert into public.materials (id, course_id, kind, title, storage_path, added_by)"
            " values (%s, %s, %s, %s, %s, (select auth.uid()))",
            (material_id, course_id, body.kind, title, path),
        )
    except psycopg.errors.InsufficientPrivilege:
        # The course is visible, so this is a student adding a textbook.
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Only admins add textbooks") from None
    token = await storage.upload_token(path)
    return PendingMaterial(
        material=Material(id=material_id, title=title, kind=body.kind, status="uploading"),
        upload=Upload(path=path, token=token),
    )


@router.post("/materials/{material_id}/queue", response_model=Material)
async def queue(
    material_id: UUID, db: UserDb, storage: Files, visit: Visit
) -> Material | JSONResponse:
    cur = await db.execute(
        "select course_id, kind::text, title, storage_path from public.materials"
        " where id = %s and status = 'uploading'",
        (material_id,),
    )
    row = await cur.fetchone()
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Material not found")
    course_id, kind, title, path = row

    stored = await storage.head(path, 8)
    if stored is None:
        raise HTTPException(status.HTTP_409_CONFLICT, "The file hasn't finished uploading.")
    head, size = stored
    content_type = detect_type(head, Path(path).suffix.lower())
    if content_type is None:
        await db.execute("delete from public.materials where id = %s", (material_id,))
        await storage.remove_prefix(f"{course_id}/{material_id}")
        # Returned rather than raised, so the delete above is committed.
        return JSONResponse({"detail": UNSUPPORTED}, status.HTTP_415_UNSUPPORTED_MEDIA_TYPE)

    try:
        await db.execute("select public.queue_material(%s)", (material_id,))
    except psycopg.errors.InsufficientPrivilege:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Material not found") from None
    await usage.log(
        db,
        visit,
        "material_uploaded",
        material_id=material_id,
        course_id=course_id,
        kind=kind,
        type="pdf" if content_type == PDF else "pptx",
        bytes=size,
    )
    return Material(id=material_id, title=title, kind=kind, status="queued")


@router.delete("/materials/{material_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove(material_id: UUID, db: UserDb, storage: Files, visit: Visit) -> Response:
    cur = await db.execute(
        "delete from public.materials where id = %s returning storage_path", (material_id,)
    )
    row = await cur.fetchone()
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Material not found")
    await usage.log(db, visit, "material_deleted", material_id=material_id)
    folder = str(Path(row[0]).parent)
    try:
        await storage.remove_prefix(f"{folder}/figures")
        await storage.remove_prefix(folder)
    except Exception:
        # The material is gone for the student; leftover files are only a storage cost.
        logger.exception("could not remove the stored files of material %s", material_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
