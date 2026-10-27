"""Admin-only operations. Accounts are invite-only: public sign-up is disabled in Supabase."""

from typing import Annotated, Literal
from uuid import UUID

import httpx
from fastapi import APIRouter, Depends, HTTPException, Response, status
from psycopg.rows import class_row
from pydantic import BaseModel, EmailStr

from engram.api.db import UserDb
from engram.config import Settings, get_settings
from engram.review import Order

router = APIRouter(prefix="/admin")


async def require_admin(db: UserDb) -> None:
    cur = await db.execute("select public.is_admin()")
    row = await cur.fetchone()
    if not row or not row[0]:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Admins only")


class InviteRequest(BaseModel):
    email: EmailStr
    display_name: str | None = None


class Invite(BaseModel):
    user_id: str
    email: EmailStr


@router.post("/invites", status_code=status.HTTP_201_CREATED, dependencies=[Depends(require_admin)])
async def invite(
    body: InviteRequest, settings: Annotated[Settings, Depends(get_settings)]
) -> Invite:
    """Email an invite link. Accepting it lands on the web app's set-password page."""
    secret = settings.supabase_secret_key.get_secret_value()
    async with httpx.AsyncClient(base_url=settings.supabase_url, timeout=10) as client:
        response = await client.post(
            "/auth/v1/invite",
            params={"redirect_to": f"{settings.web_url.rstrip('/')}/auth/set-password"},
            headers={"apikey": secret, "Authorization": f"Bearer {secret}"},
            json={"email": body.email, "data": {"display_name": body.display_name}},
        )
    if response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT:
        raise HTTPException(status.HTTP_409_CONFLICT, "That email already has an account")
    response.raise_for_status()
    user = response.json()
    return Invite(user_id=user["id"], email=user["email"])


class Person(BaseModel):
    id: UUID
    display_name: str | None
    role: Literal["student", "admin"]
    review_order: Order


class ReviewOrder(BaseModel):
    order: Order


@router.get("/people", dependencies=[Depends(require_admin)])
async def people(db: UserDb) -> list[Person]:
    """Everyone with an account, with the review order each is trying."""
    async with db.cursor(row_factory=class_row(Person)) as cur:
        await cur.execute(
            "select id, display_name, role::text as role, review_order::text as review_order"
            " from public.profiles order by role, display_name nulls last, created_at"
        )
        return await cur.fetchall()


@router.put(
    "/people/{person_id}/review-order",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_admin)],
)
async def set_review_order(person_id: UUID, body: ReviewOrder, db: UserDb) -> Response:
    cur = await db.execute(
        "update public.profiles set review_order = %s where id = %s", (body.order, person_id)
    )
    if cur.rowcount == 0:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No such person")
    return Response(status_code=status.HTTP_204_NO_CONTENT)
