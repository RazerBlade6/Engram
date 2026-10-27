"""The `generate_cards` job, queued when a student marks a chapter covered.

A chapter's passages are sent in batches, side by side, and its cards are stored together
once every batch is done. If the chapter is unmarked meanwhile, the job stops and stores
nothing; cards that already exist are kept. A chapter that already has cards (marked, then
unmarked and marked again) gets no second set.
"""

import asyncio
import json
import logging
import re
from collections.abc import Awaitable, Callable
from typing import Any

from psycopg import AsyncConnection

from engram.cards.generate import (
    MAX_TOKENS,
    PROMPT_VERSION,
    SYSTEM,
    Card,
    CardSet,
    Passage,
    accept,
    batches,
    prompt_for,
)
from engram.config import Settings
from engram.errors import PermanentError
from engram.llm import Job as LLMJob
from engram.llm import Provider, ProviderError, Router, TextPart, Usage
from engram.usage import record
from engram.worker.queue import Handler, Job

logger = logging.getLogger(__name__)

KIND = "generate_cards"
CONCURRENCY = 4

# End-of-chapter material repeats the chapter or asks questions about it: no new cards.
_SKIPPED = re.compile(
    r"^(\d+(\.\d+)*\s+)?(key terms|summary|review questions|critical thinking questions"
    r"|personal application questions|chapter outline|references|exercises|glossary)$",
    re.IGNORECASE,
)

_PASSAGES = """
with recursive tree as (
  select id, id as grp, title as grp_title, 0 as depth
    from public.sections where id = %(section)s
  union all
  select s.id,
         case when t.depth = 0 then s.id else t.grp end,
         case when t.depth = 0 then s.title else t.grp_title end,
         t.depth + 1
    from public.sections s join tree t on s.parent_id = t.id
)
select c.id::text, t.grp::text, t.grp_title, c.kind::text, c.heading_path, c.content, c.locations
  from public.chunks c join tree t on t.id = c.section_id
 order by c.ordinal
"""


class Unmarked(Exception):
    """The chapter was unmarked while its cards were being made."""


def make_handler(settings: Settings, *, router: Router | None = None) -> Handler:
    async def handle(job: Job) -> None:
        section_id = str(job.payload["section_id"])
        async with await AsyncConnection.connect(settings.database_url, autocommit=True) as conn:
            try:
                await generate(conn, section_id, router=router or Router(settings))
            except Exception as exc:
                if isinstance(exc, PermanentError) or job.attempts >= job.max_attempts:
                    await conn.execute(
                        "update public.covered_sections set cards_status = 'failed'"
                        " where section_id = %s",
                        (section_id,),
                    )
                raise

    return handle


async def _covered(conn: AsyncConnection[Any], section_id: str) -> bool:
    cur = await conn.execute(
        "select 1 from public.covered_sections where section_id = %s", (section_id,)
    )
    return await cur.fetchone() is not None


async def generate(conn: AsyncConnection[Any], section_id: str, *, router: Router) -> None:
    cur = await conn.execute(
        "select s.material_id::text, s.title,"
        " exists (select 1 from public.cards k where k.section_id = s.id)"
        " from public.sections s join public.covered_sections c on c.section_id = s.id"
        " where s.id = %s",
        (section_id,),
    )
    row = await cur.fetchone()
    if row is None:
        logger.info("section %s is no longer covered; nothing to do", section_id)
        return
    material_id, chapter, has_cards = row
    if has_cards:
        await _finish(conn, section_id, material_id, [], router)
        return

    provider, model = router.provider_for(LLMJob.CARD_GENERATION)
    usage = Usage()
    try:
        cards = await make_cards(
            chapter,
            await load_passages(conn, section_id),
            provider,
            model,
            usage=usage,
            still_covered=lambda: _covered(conn, section_id),
        )
    except Unmarked:
        logger.info("section %s was unmarked; stopped generating", section_id)
        return
    finally:
        # Recorded however the run ended: every finished request was billed.
        await record(conn, KIND, usage, material_id=material_id, section_id=section_id)
    await _finish(conn, section_id, material_id, cards, router)


async def load_passages(conn: AsyncConnection[Any], section_id: str) -> list[Passage]:
    """The chapter's passages in reading order, minus end-of-chapter material."""
    async with conn.cursor() as cur:
        await cur.execute(_PASSAGES, {"section": section_id})
        return [
            Passage(chunk_id, group, kind, heading_path, content, locations)
            for chunk_id, group, group_title, kind, heading_path, content, locations in (
                await cur.fetchall()
            )
            if not _SKIPPED.match(group_title.strip())
        ]


async def make_cards(
    chapter: str,
    passages: list[Passage],
    provider: Provider,
    model: str,
    *,
    usage: Usage,
    still_covered: Callable[[], Awaitable[bool]],
) -> list[Card]:
    """Cards for a chapter's passages, one request per batch, several at a time. Raises
    `Unmarked` as soon as `still_covered` says no, cancelling requests in flight."""
    gate = asyncio.Semaphore(CONCURRENCY)
    work = batches(passages)

    async def one(batch: list[Passage]) -> list[Card] | None:
        async with gate:
            if not await still_covered():
                raise Unmarked
            try:
                result = await provider.structured(
                    model,
                    system=SYSTEM,
                    parts=[TextPart(prompt_for(chapter, batch))],
                    schema=CardSet,
                    max_tokens=MAX_TOKENS,
                    usage=usage,
                )
            except ProviderError as exc:
                logger.warning("%s, %s passages: %s", chapter, len(batch), exc)
                return None
        cards, dropped = accept(result.cards, batch)
        if dropped:
            logger.info("%s: dropped %s", chapter, dropped)
        return cards

    try:
        async with asyncio.TaskGroup() as group:
            tasks = [group.create_task(one(b)) for b in work]
    except ExceptionGroup as exc:
        # Unwrapped, so callers can catch `Unmarked` and the worker still sees e.g. a
        # permanent error as permanent.
        raise (exc.subgroup(Unmarked) or exc).exceptions[0] from exc
    results = [t.result() for t in tasks]
    if work and all(r is None for r in results):
        raise ProviderError(f"no batch of {chapter!r} produced cards")
    return [card for r in results if r for card in r]


async def _finish(
    conn: AsyncConnection[Any],
    section_id: str,
    material_id: str,
    cards: list[Card],
    router: Router,
) -> None:
    """Store the cards and mark the chapter ready, unless it was unmarked or already has
    cards from another run."""
    async with conn.transaction():
        cur = await conn.execute(
            "select 1 from public.covered_sections where section_id = %s for update",
            (section_id,),
        )
        if await cur.fetchone() is None:
            logger.info("section %s was unmarked; discarding %s cards", section_id, len(cards))
            return
        cur = await conn.execute(
            "select exists (select 1 from public.cards where section_id = %s)", (section_id,)
        )
        exists = await cur.fetchone()
        if cards and exists and not exists[0]:
            async with conn.cursor() as icur:
                await icur.executemany(
                    "insert into public.cards (material_id, section_id, ordinal, kind, concept,"
                    " prompt, answer, choices, sources, generated_by, prompt_version)"
                    " values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
                    [
                        (
                            material_id,
                            section_id,
                            i,
                            c.kind,
                            c.concept,
                            c.prompt,
                            c.answer,
                            c.choices,
                            json.dumps(c.sources),
                            str(router.model_for(LLMJob.CARD_GENERATION)),
                            PROMPT_VERSION,
                        )
                        for i, c in enumerate(cards)
                    ],
                )
        await conn.execute(
            "update public.covered_sections set cards_status = 'ready' where section_id = %s",
            (section_id,),
        )
    logger.info("section %s: stored %s cards", section_id, len(cards))
