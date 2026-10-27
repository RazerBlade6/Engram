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
from collections.abc import AsyncIterator
from functools import lru_cache
from typing import Annotated, Any, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import StreamingResponse
from psycopg import AsyncConnection
from psycopg_pool import AsyncConnectionPool
from pydantic import BaseModel, Field

from engram.api.db import UserDbUntilStreaming, get_pool
from engram.chat.answer import Cited, Outside, Text, answer, search_text
from engram.chat.retrieve import search
from engram.config import Settings, get_settings
from engram.embeddings import get_embedder
from engram.llm import Job, Router, Usage
from engram.llm.base import Turn
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


@router.post("/courses/{course_id}/ask", response_class=StreamingResponse)
async def ask(
    course_id: UUID,
    body: Ask,
    db: UserDbUntilStreaming,
    request: Request,
    llm: Llm,
    settings: Annotated[Settings, Depends(get_settings)],
) -> StreamingResponse:
    cur = await db.execute("select 1 from public.courses where id = %s", (course_id,))
    if await cur.fetchone() is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Course not found")
    history = [Turn(t.role, t.text) for t in body.history]
    query = search_text(body.question, history)
    embedder = await asyncio.to_thread(get_embedder, settings.embedding_model)
    embedding = await asyncio.to_thread(embedder.query, query)
    # Everything read as the student happens here, before the response starts streaming.
    passages = await search(db, course_id, query, embedding)
    provider, model = llm.provider_for(Job.CHAT)

    async def events() -> AsyncIterator[str]:
        usage = Usage()
        cited = outside = False
        try:
            async for event in answer(provider, model, body.question, history, passages, usage):
                match event:
                    case Text(block, text):
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
        except Exception:
            # Whatever went wrong (refusal, overload, credentials), the student sees one message.
            logger.exception("chat answer failed")
            yield _event("error", {"message": "The answer couldn't be finished. Please ask again."})
        finally:
            # Shielded, so it's still recorded if the student leaves mid-answer.
            await asyncio.shield(_record(get_pool(request), usage))

    return StreamingResponse(
        events(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


async def _record(pool: AsyncConnectionPool[AsyncConnection[Any]], usage: Usage) -> None:
    try:
        async with pool.connection() as conn:
            await record(conn, "chat", usage)
    except Exception:
        logger.exception("couldn't record chat usage")
