"""Asking a question about a course. The answer streams as server-sent events:

- `text` {block, text}: more of the answer. Text comes in blocks; a cited block's citations
  follow its text.
- `source` {number, chunk_id, material_id, book, heading_path, page}: a passage, the first
  time the answer cites it.
- `cite` {block, source, quote}: `block` is supported by source `source`, which says `quote`.
- `outside` {}: the answer isn't from the course materials; sent before its text.
- `done` {grounded}: false when the answer is outside the materials or cites nothing, so it
  is labeled as not from the student's course materials.
- `error` {message}: the answer couldn't be finished.

Questions and answers aren't stored: the client keeps the conversation and sends the recent
turns back with each question. Only the tokens used are recorded, with no user attached.
"""

import asyncio
import json
import logging
import time
from collections.abc import AsyncIterator
from functools import lru_cache
from typing import Annotated, Any, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import StreamingResponse
from psycopg import AsyncConnection
from psycopg_pool import AsyncConnectionPool
from pydantic import BaseModel, Field

from engram.api.auth import CurrentUser
from engram.api.db import UserDbUntilStreaming, get_pool
from engram.api.errors import describe
from engram.api.errors import record as record_error
from engram.api.routes.review import Today
from engram.chat.answer import Cited, Outside, Text, answer, search_text
from engram.chat.retrieve import search
from engram.config import Settings, get_settings
from engram.embeddings import get_embedder
from engram.llm import Job, Router, Usage
from engram.llm.base import Turn
from engram.review import Day
from engram.usage import record

logger = logging.getLogger(__name__)

router = APIRouter()


@lru_cache
def _router() -> Router:
    return Router(get_settings())


def get_llm() -> Router:
    return _router()


Llm = Annotated[Router, Depends(get_llm)]


class AskTurn(BaseModel):
    role: Literal["user", "assistant"]
    text: str = Field(max_length=8000)


class Ask(BaseModel):
    question: str = Field(min_length=1, max_length=2000)
    # The conversation so far, oldest first; the client sends only the last few turns.
    history: list[AskTurn] = Field(default=[], max_length=12)


def _event(name: str, data: dict[str, Any]) -> str:
    return f"event: {name}\ndata: {json.dumps(data, default=str)}\n\n"


ROUTE = "/courses/{course_id}/ask"
# Questions a student may ask a day (D96); admins have no limit.
DAILY_QUESTIONS = 100


@router.post(ROUTE, response_class=StreamingResponse)
async def ask(
    course_id: UUID,
    body: Ask,
    db: UserDbUntilStreaming,
    request: Request,
    llm: Llm,
    settings: Annotated[Settings, Depends(get_settings)],
    user: CurrentUser,
    day: Today,
) -> StreamingResponse:
    cur = await db.execute(
        "select public.is_admin() from public.courses where id = %s", (course_id,)
    )
    found = await cur.fetchone()
    if found is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Course not found")
    if not found[0] and not await _count_question(get_pool(request), user.id, day):
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS,
            f"You've asked {DAILY_QUESTIONS} questions today, the most for one day."
            " You can ask more tomorrow.",
        )
    started = time.perf_counter()
    history = [Turn(t.role, t.text) for t in body.history]
    query = search_text(body.question, history)
    embedder = await asyncio.to_thread(get_embedder, settings.embedding_model)
    embedding = await asyncio.to_thread(embedder.query, query)
    embedded = time.perf_counter()
    # Everything read as the student happens here, before the response starts streaming.
    passages = await search(db, course_id, query, embedding)
    searched = time.perf_counter()
    provider, model = llm.provider_for(Job.CHAT)

    async def events() -> AsyncIterator[str]:
        usage = Usage()
        cited = outside = False
        first_text: float | None = None
        # The response has started with 200, so the error middleware can't see a failure.
        failure: str | None = None
        try:
            async for event in answer(provider, model, body.question, history, passages, usage):
                match event:
                    case Text(block, text):
                        if first_text is None:
                            first_text = time.perf_counter()
                        yield _event("text", {"block": block, "text": text})
                    case Outside():
                        outside = True
                        yield _event("outside", {})
                    case Cited(block, source, first, quote):
                        if first:
                            p = source.passage
                            yield _event(
                                "source",
                                {
                                    "number": source.number,
                                    "chunk_id": p.chunk_id,
                                    "material_id": p.material_id,
                                    "book": p.book,
                                    "heading_path": p.heading_path,
                                    "page": p.page,
                                },
                            )
                        cited = True
                        yield _event(
                            "cite", {"block": block, "source": source.number, "quote": quote}
                        )
            yield _event("done", {"grounded": cited and not outside})
        except Exception as exc:
            # Whatever went wrong (refusal, overload, credentials), the student sees one message.
            logger.exception("chat answer failed")
            failure = describe(exc)
            yield _event("error", {"message": "The answer couldn't be finished. Please ask again."})
        finally:
            # Where the time went, for finding what makes an answer slow. Timings and sizes
            # only: never the question or the answer.
            logger.info(
                "ask timing: embed %d ms, search %d ms, first text %s ms, total %d ms;"
                " %d passages, %d history turns, %d tokens in, %d out",
                _ms(started, embedded),
                _ms(embedded, searched),
                _ms(searched, first_text) if first_text is not None else "-",
                _ms(started, time.perf_counter()),
                len(passages),
                len(history),
                usage.input_tokens,
                usage.output_tokens,
            )
            # Shielded, so it's still recorded if the student leaves mid-answer.
            await asyncio.shield(_record(get_pool(request), usage))
            if failure is not None:
                await asyncio.shield(
                    record_error(get_pool(request), "POST", ROUTE, failure, status=None)
                )

    return StreamingResponse(
        events(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


async def _count_question(
    pool: AsyncConnectionPool[AsyncConnection[Any]], user_id: str, day: Day
) -> bool:
    """Count a question against the student's day; False if they've reached the limit."""
    async with pool.connection() as conn:
        cur = await conn.execute(
            "insert into public.daily_questions (user_id, day, questions) values (%s, %s, 1)"
            " on conflict (user_id, day) do update"
            " set questions = daily_questions.questions + 1"
            " where daily_questions.questions < %s"
            " returning questions",
            (user_id, day.date, DAILY_QUESTIONS),
        )
        return await cur.fetchone() is not None


def _ms(start: float, end: float) -> int:
    return round((end - start) * 1000)


async def _record(pool: AsyncConnectionPool[AsyncConnection[Any]], usage: Usage) -> None:
    try:
        async with pool.connection() as conn:
            await record(conn, "chat", usage)
    except Exception:
        logger.exception("couldn't record chat usage")
