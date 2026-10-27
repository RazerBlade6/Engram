"""Events only the browser sees, such as page views and how quickly an answer started."""

from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter
from pydantic import BaseModel, Field

from engram.api import usage
from engram.api.db import UserDb
from engram.api.usage import Visit

router = APIRouter()

Ms = Annotated[int, Field(ge=0, le=3_600_000)]


class SessionStart(BaseModel):
    name: Literal["session_start"]
    # Viewport width, to tell laptops from phones.
    width: Annotated[int, Field(ge=0, le=10_000)]


class PageView(BaseModel):
    name: Literal["page_view"]
    # The route with ids replaced, e.g. "/courses/[id]".
    page: Annotated[str, Field(pattern=r"^/[a-z0-9/_\[\]-]{0,99}$")]


class SourceOpened(BaseModel):
    name: Literal["source_opened"]
    origin: Literal["chat", "review"]
    page_image: bool


class ChatQuestion(BaseModel):
    name: Literal["chat_question"]
    course_id: UUID
    first_text_ms: Ms | None
    total_ms: Ms
    grounded: bool
    outside: bool
    sources: Annotated[int, Field(ge=0, le=50)]
    follow_up: bool
    failed: bool


BrowserEvent = Annotated[
    SessionStart | PageView | SourceOpened | ChatQuestion, Field(discriminator="name")
]


class Logged(BaseModel):
    # False when the user hasn't agreed to logging: the browser stops sending for the visit.
    logged: bool


@router.post("/events")
async def record(event: BrowserEvent, db: UserDb, visit: Visit) -> Logged:
    if not await usage.logs_usage(db):
        return Logged(logged=False)
    await usage.log(db, visit, event.name, **event.model_dump(exclude={"name"}))
    return Logged(logged=True)
