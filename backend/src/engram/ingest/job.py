"""The `ingest_material` job: download, parse, describe figures, embed, store."""

import asyncio
import logging
import tempfile
from collections.abc import Callable
from contextlib import AsyncExitStack
from dataclasses import replace
from pathlib import Path
from typing import Any

from psycopg import AsyncConnection

from engram.config import Settings
from engram.embeddings import Embedder, get_embedder
from engram.ingest import store
from engram.ingest.describe import describe_figures, figure_text
from engram.ingest.failures import Unreadable
from engram.ingest.model import Chunk, ParsedMaterial
from engram.llm import Job as LLMJob
from engram.llm import Router, Usage
from engram.storage import Storage
from engram.usage import record
from engram.worker.queue import Handler, Job

logger = logging.getLogger(__name__)

KIND = "ingest_material"

Parser = Callable[[Path, bool], ParsedMaterial]


def _default_parser(path: Path, slides: bool) -> ParsedMaterial:
    from engram.ingest.parse import parse  # loads Docling and its models; worker only

    return parse(path, slides=slides)


def make_handler(
    settings: Settings,
    *,
    router: Router | None = None,
    storage: Storage | None = None,
    embedder: Embedder | None = None,
    parser: Parser = _default_parser,
) -> Handler:
    async def handle(job: Job) -> None:
        material_id = str(job.payload["material_id"])
        async with (
            AsyncExitStack() as stack,
            await AsyncConnection.connect(settings.database_url, autocommit=True) as conn,
        ):
            if storage is None:
                files: Storage = await stack.enter_async_context(Storage(settings))
            else:
                files = storage
            # On failure the material stays 'processing' while the job is retried; once it
            # fails for good, the database marks it failed (migration job_failed_marks_work).
            try:
                await ingest(
                    conn,
                    material_id,
                    router=router or Router(settings),
                    storage=files,
                    embedder=embedder or get_embedder(settings.embedding_model),
                    parser=parser,
                )
            except Unreadable as exc:
                # Permanent, so the job fails at once and the trigger keeps this reason.
                await conn.execute(
                    "update public.materials set failure = %s where id = %s",
                    (exc.reason, material_id),
                )
                raise

    return handle


async def ingest(
    conn: AsyncConnection[Any],
    material_id: str,
    *,
    router: Router,
    storage: Storage,
    embedder: Embedder,
    parser: Parser,
) -> None:
    cur = await conn.execute(
        "update public.materials set status = 'processing', stage = 'parsing', error = null,"
        " failure = null where id = %s and status <> 'ready'"
        " returning storage_path, kind::text",
        (material_id,),
    )
    row = await cur.fetchone()
    if row is None:
        cur = await conn.execute("select 1 from public.materials where id = %s", (material_id,))
        if await cur.fetchone() is None:
            raise LookupError(f"material {material_id} not found")
        # Already read: a job run again (after a lost connection, say) would replace every
        # chunk and pay for every figure again (D91).
        logger.info("material %s is already ready; not reading it again", material_id)
        return
    storage_path, kind = row
    slides = kind == "slides"

    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / Path(storage_path).name
        data = await storage.download(storage_path)
        await asyncio.to_thread(path.write_bytes, data)
        parsed = await asyncio.to_thread(parser, path, slides)
    if not parsed.figures and not any(c.text.strip() for c in parsed.chunks):
        # Slides of nothing but blank pages, or a presentation without a word in it.
        raise Unreadable("no_text", f"no text or figures in {parsed.page_count} pages")
    logger.info(
        "material %s: %s pages, %s sections, %s figures, %s chunks",
        material_id,
        parsed.page_count,
        len(parsed.sections),
        len(parsed.figures),
        len(parsed.chunks),
    )

    await _stage(conn, material_id, "describing" if parsed.figures else "indexing")
    usage = Usage()
    try:
        descriptions = await describe_figures(parsed.figures, router, usage)
    finally:
        await record(conn, "describe_figures", usage, material_id=material_id)
    figure_prefix = f"{Path(storage_path).parent}/figures"
    await storage.remove_prefix(figure_prefix)
    figure_paths = []
    for figure in parsed.figures:
        figure_path = f"{figure_prefix}/{figure.ordinal}.png"
        await storage.upload(figure_path, figure.image_png, "image/png")
        figure_paths.append(figure_path)

    figure_chunks = [
        Chunk(
            ordinal=len(parsed.chunks) + i,
            kind="figure",
            text=figure_text(figure, description),
            heading_path=figure.context,
            locations=[figure.location],
            section=figure.section,
            figure=figure.ordinal,
        )
        for i, (figure, description) in enumerate(zip(parsed.figures, descriptions, strict=True))
    ]
    chunks = [c for c in [*parsed.chunks, *figure_chunks] if c.text.strip()]
    chunks = [replace(c, ordinal=i) for i, c in enumerate(chunks)]
    await _stage(conn, material_id, "indexing")
    embeddings = await asyncio.to_thread(embedder.passages, [c.content for c in chunks])

    await store.replace_material_content(
        conn,
        material_id,
        parsed,
        descriptions=descriptions,
        described_by=str(router.model_for(LLMJob.FIGURE_DESCRIPTION)),
        figure_paths=figure_paths,
        chunks=chunks,
        embeddings=embeddings,
        embedding_model=embedder.model_name,
    )


async def _stage(conn: AsyncConnection[Any], material_id: str, stage: str) -> None:
    """Which step the material is on, for the course page (migration retry_cards_and_stages)."""
    await conn.execute("update public.materials set stage = %s where id = %s", (stage, material_id))
