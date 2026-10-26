from typing import Literal

from fastapi import APIRouter, HTTPException, status
from psycopg.rows import class_row
from pydantic import BaseModel

from engram.api.db import UserDb

router = APIRouter()


class Profile(BaseModel):
    id: str
    display_name: str | None
    role: Literal["student", "admin"]


@router.get("/me")
async def me(db: UserDb) -> Profile:
    async with db.cursor(row_factory=class_row(Profile)) as cur:
        await cur.execute(
            "select id::text, display_name, role::text from public.profiles"
            " where id = (select auth.uid())"
        )
        profile = await cur.fetchone()
    if profile is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Profile not found")
    return profile
