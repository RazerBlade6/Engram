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
from engram.ingest.model import Chunk, ParsedMaterial
from engram.llm import Job as LLMJob
from engram.llm import Router
from engram.storage import Storage
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
            try:
                await ingest(
                    conn,
                    material_id,
                    router=router or Router(settings),
                    storage=files,
                    embedder=embedder or get_embedder(settings.embedding_model),
                    parser=parser,
                )
            except Exception as exc:
                await conn.execute(
                    "update public.materials set status = 'failed', error = %s where id = %s",
                    (f"{type(exc).__name__}: {exc}", material_id),
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
        "update public.materials set status = 'processing', error = null where id = %s"
        " returning storage_path, kind::text",
        (material_id,),
    )
    row = await cur.fetchone()
    if row is None:
        raise LookupError(f"material {material_id} not found")
    storage_path, kind = row
    slides = kind == "slides"

    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / Path(storage_path).name
        data = await storage.download(storage_path)
        await asyncio.to_thread(path.write_bytes, data)
        parsed = await asyncio.to_thread(parser, path, slides)
    logger.info(
        "material %s: %s pages, %s sections, %s figures, %s chunks",
        material_id,
        parsed.page_count,
        len(parsed.sections),
        len(parsed.figures),
        len(parsed.chunks),
    )

    descriptions = await describe_figures(parsed.figures, router)
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
