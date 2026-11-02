"""Describes figures with a vision model, so diagrams become searchable and their labels can
drive image-occlusion cards later. Descriptions are kept by image, so a figure is paid for
once however often its material is uploaded or read (D96)."""

import asyncio
import hashlib
import logging
from typing import Any, Literal

from psycopg import AsyncConnection
from pydantic import BaseModel, Field

from engram.ingest.model import Figure
from engram.llm import ImagePart, Job, ProviderError, Router, TextPart, Usage

logger = logging.getLogger(__name__)

CONCURRENCY = 4

SYSTEM = """You describe figures from university course materials so students can find them \
by searching and study from them.

Describe only what the figure shows. Use the caption and section for context, but do not add \
facts that are not visible in the figure. Write plainly for a student; do not start with \
"This image" or "The figure"."""


class FigureDescription(BaseModel):
    kind: Literal["diagram", "chart", "photo", "table", "equation", "other"]
    description: str = Field(
        description="Two to four sentences: what the figure shows and what it teaches."
    )
    labels: list[str] = Field(
        description="Every text label written inside the figure, verbatim, in reading order."
        " Empty if there are none."
    )


async def describe_figures(
    figures: list[Figure], router: Router, usage: Usage | None = None
) -> list[FigureDescription | None]:
    """One description per figure, in order. A figure the model declines gets None; any other
    error (bad credentials, an outage after retries) fails the whole batch."""
    provider, model = router.provider_for(Job.FIGURE_DESCRIPTION)
    gate = asyncio.Semaphore(CONCURRENCY)

    async def one(figure: Figure) -> FigureDescription | None:
        context = " > ".join(figure.context) or "unknown"
        prompt = f"Section: {context}\nCaption: {figure.caption or 'none'}"
        async with gate:
            try:
                return await provider.structured(
                    model,
                    system=SYSTEM,
                    parts=[ImagePart(figure.image_png), TextPart(prompt)],
                    schema=FigureDescription,
                    usage=usage,
                )
            except ProviderError as exc:
                logger.warning(
                    "figure %s on page %s: %s", figure.ordinal, figure.location.page, exc
                )
                return None

    return list(await asyncio.gather(*(one(f) for f in figures)))


async def describe_reusing(
    conn: AsyncConnection[Any], figures: list[Figure], router: Router, usage: Usage | None = None
) -> list[FigureDescription | None]:
    """As `describe_figures`, but a figure whose image the same model has described before
    reuses that description, and an image that appears twice is described once."""
    model = str(router.model_for(Job.FIGURE_DESCRIPTION))
    hashes = [hashlib.sha256(f.image_png).hexdigest() for f in figures]
    cur = await conn.execute(
        "select image_sha256, kind, description, labels from public.figure_descriptions"
        " where model = %s and image_sha256 = any(%s)",
        (model, sorted(set(hashes))),
    )
    known: dict[str, FigureDescription | None] = {
        sha: FigureDescription(kind=kind, description=description, labels=labels)
        for sha, kind, description, labels in await cur.fetchall()
    }
    # The first figure with each image not described yet.
    new = {sha: figure for sha, figure in zip(hashes, figures, strict=True) if sha not in known}
    if new:
        logger.info("describing %s figures; %s reused", len(new), len(figures) - len(new))
        described = await describe_figures(list(new.values()), router, usage)
        fresh = dict(zip(new, described, strict=True))
        async with conn.cursor() as icur:
            await icur.executemany(
                "insert into public.figure_descriptions"
                " (image_sha256, model, kind, description, labels) values (%s, %s, %s, %s, %s)"
                " on conflict do nothing",
                [
                    (sha, model, d.kind, d.description, d.labels)
                    for sha, d in fresh.items()
                    # A figure the model declined is asked about again next time.
                    if d is not None
                ],
            )
        known |= fresh
    return [known[sha] for sha in hashes]


def figure_text(figure: Figure, description: FigureDescription | None) -> str:
    """The searchable text for a figure chunk."""
    parts = [figure.caption or ""]
    if description:
        parts.append(description.description)
        if description.labels:
            parts.append("Labels: " + ", ".join(description.labels))
    return "\n\n".join(p for p in parts if p)
