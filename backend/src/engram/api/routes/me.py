from datetime import datetime
from typing import Literal

from fastapi import APIRouter, HTTPException, Response, status
from psycopg.rows import class_row
from pydantic import BaseModel

from engram.api.db import UserDb

router = APIRouter()


class Profile(BaseModel):
    id: str
    display_name: str | None
    role: Literal["student", "admin"]
    # When they finished or skipped the welcome tour; null until then (D60).
    welcomed_at: datetime | None


@router.get("/me")
async def me(db: UserDb) -> Profile:
    async with db.cursor(row_factory=class_row(Profile)) as cur:
        await cur.execute(
            "select id::text, display_name, role::text, welcomed_at from public.profiles"
            " where id = (select auth.uid())"
        )
        profile = await cur.fetchone()
    if profile is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Profile not found")
    return profile


@router.put("/me/welcomed", status_code=status.HTTP_204_NO_CONTENT)
async def welcomed(db: UserDb) -> Response:
    """Records that the welcome tour was seen, so it doesn't show again on another device."""
    await db.execute("select public.mark_welcomed()")
    return Response(status_code=status.HTTP_204_NO_CONTENT)
