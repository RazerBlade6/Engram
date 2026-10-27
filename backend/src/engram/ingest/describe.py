"""Describes figures with a vision model, so diagrams become searchable and their labels can
drive image-occlusion cards later."""

import asyncio
import logging
from typing import Literal

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


def figure_text(figure: Figure, description: FigureDescription | None) -> str:
    """The searchable text for a figure chunk."""
    parts = [figure.caption or ""]
    if description:
        parts.append(description.description)
        if description.labels:
            parts.append("Labels: " + ", ".join(description.labels))
    return "\n\n".join(p for p in parts if p)
