"""Students add slides to a course and remove them.

An upload is stored and queued for ingestion in one request: the material row, the stored
file, and the ingestion job (via `queue_material`) all belong to the request's transaction.
"""

import asyncio
import logging
import zipfile
from pathlib import Path
from typing import IO, Annotated
from uuid import UUID, uuid4

import psycopg
from fastapi import APIRouter, Depends, HTTPException, Request, Response, UploadFile, status

from engram.api import usage
from engram.api.db import UserDb
from engram.api.routes.courses import Material
from engram.api.usage import Visit
from engram.storage import Storage, safe_filename

logger = logging.getLogger(__name__)

router = APIRouter()

MAX_UPLOAD_BYTES = 100 * 1024 * 1024  # generous for lecture slides; textbooks go via admins

PDF = "application/pdf"
PPTX = "application/vnd.openxmlformats-officedocument.presentationml.presentation"


def get_storage(request: Request) -> Storage:
    storage: Storage = request.app.state.storage
    return storage


Files = Annotated[Storage, Depends(get_storage)]


def detect_type(file: IO[bytes]) -> str | None:
    """PDF or PowerPoint, judged by the content rather than the file name."""
    head = file.read(5)
    file.seek(0)
    if head.startswith(b"%PDF-"):
        return PDF
    if head.startswith(b"PK"):
        try:
            with zipfile.ZipFile(file) as archive:
                if "ppt/presentation.xml" in archive.namelist():
                    return PPTX
        except zipfile.BadZipFile:
            return None
        finally:
            file.seek(0)
    return None


def title_from(filename: str) -> str:
    return Path(filename).stem.replace("_", " ").strip()[:200] or "Slides"


@router.post("/courses/{course_id}/materials", status_code=status.HTTP_201_CREATED)
async def upload(
    course_id: UUID, file: UploadFile, db: UserDb, storage: Files, visit: Visit
) -> Material:
    cur = await db.execute("select 1 from public.courses where id = %s", (course_id,))
    if await cur.fetchone() is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Course not found")

    if file.size is not None and file.size > MAX_UPLOAD_BYTES:
        raise HTTPException(
            status.HTTP_413_CONTENT_TOO_LARGE,
            f"That file is over {MAX_UPLOAD_BYTES // 2**20} MB.",
        )
    content_type = await asyncio.to_thread(detect_type, file.file)
    if content_type is None:
        raise HTTPException(
            status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            "Engram can read PDF and PowerPoint (.pptx) files.",
        )

    filename = file.filename or "slides"
    suffix = ".pdf" if content_type == PDF else ".pptx"
    material_id = uuid4()
    path = f"{course_id}/{material_id}/{safe_filename(Path(filename).stem + suffix)}"
    title = title_from(filename)
    try:
        await db.execute(
            "insert into public.materials (id, course_id, kind, title, storage_path, added_by)"
            " values (%s, %s, 'slides', %s, %s, (select auth.uid()))",
            (material_id, course_id, title, path),
        )
    except psycopg.errors.InsufficientPrivilege:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Course not found") from None

    data = await asyncio.to_thread(file.file.read)
    await usage.log(
        db,
        visit,
        "material_uploaded",
        material_id=material_id,
        course_id=course_id,
        type="pdf" if content_type == PDF else "pptx",
        bytes=len(data),
    )
    await storage.upload(path, data, content_type)
    try:
        await db.execute("select public.queue_material(%s)", (material_id,))
    except Exception:
        await storage.remove_prefix(f"{course_id}/{material_id}")
        raise
    return Material(id=material_id, title=title, kind="slides", status="queued")


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
