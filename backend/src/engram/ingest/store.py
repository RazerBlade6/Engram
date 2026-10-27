"""Writes a parsed material in one transaction, replacing anything from a previous run."""

import json
from typing import Any

from psycopg import AsyncConnection

from engram.ingest.describe import FigureDescription
from engram.ingest.model import Chunk, ParsedMaterial


def _vector(values: list[float]) -> str:
    return "[" + ",".join(f"{v:.6f}" for v in values) + "]"


async def replace_material_content(
    conn: AsyncConnection[Any],
    material_id: str,
    parsed: ParsedMaterial,
    *,
    descriptions: list[FigureDescription | None],
    described_by: str,
    figure_paths: list[str],
    chunks: list[Chunk],
    embeddings: list[list[float]],
    embedding_model: str,
) -> None:
    async with conn.transaction():
        # Coverage hangs off sections, which are about to be replaced. Keep it for every
        # section that comes back with the same level and title.
        cur = await conn.execute(
            "select s.level, s.title, c.covered_at, c.covered_by, c.cards_status"
            " from public.covered_sections c join public.sections s on s.id = c.section_id"
            " where s.material_id = %s",
            (material_id,),
        )
        coverage = {(level, title): rest for level, title, *rest in await cur.fetchall()}
        # So do cards, which lose their chapter when it is deleted; re-attach them the same way.
        cur = await conn.execute(
            "select s.level, s.title, array_agg(k.id)"
            " from public.cards k join public.sections s on s.id = k.section_id"
            " where s.material_id = %s group by s.level, s.title",
            (material_id,),
        )
        cards = {(level, title): ids for level, title, ids in await cur.fetchall()}

        for table in ("chunks", "figures", "sections"):
            await conn.execute(f"delete from public.{table} where material_id = %s", (material_id,))

        section_ids: dict[int, str] = {}
        for s in parsed.sections:
            cur = await conn.execute(
                "insert into public.sections"
                " (material_id, parent_id, ordinal, level, title, page_start, page_end)"
                " values (%s, %s, %s, %s, %s, %s, %s) returning id",
                (
                    material_id,
                    section_ids.get(s.parent) if s.parent is not None else None,
                    s.ordinal,
                    s.level,
                    s.title,
                    s.page_start,
                    s.page_end,
                ),
            )
            row = await cur.fetchone()
            assert row is not None
            section_ids[s.ordinal] = str(row[0])
            if covered := coverage.pop((s.level, s.title), None):
                # A 'pending' mark queues generation again: the old job's section is gone.
                await conn.execute(
                    "insert into public.covered_sections"
                    " (section_id, covered_at, covered_by, cards_status) values (%s, %s, %s, %s)",
                    (row[0], *covered),
                )
            if card_ids := cards.pop((s.level, s.title), None):
                await conn.execute(
                    "update public.cards set section_id = %s where id = any(%s)",
                    (row[0], card_ids),
                )

        figure_ids: dict[int, str] = {}
        for f, description, path in zip(parsed.figures, descriptions, figure_paths, strict=True):
            cur = await conn.execute(
                "insert into public.figures (material_id, section_id, ordinal, page, bbox,"
                " caption, description, labels, storage_path, described_by)"
                " values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s) returning id",
                (
                    material_id,
                    section_ids.get(f.section) if f.section is not None else None,
                    f.ordinal,
                    f.location.page,
                    list(f.location.bbox),
                    f.caption,
                    description.description if description else None,
                    description.labels if description else [],
                    path,
                    described_by if description else None,
                ),
            )
            row = await cur.fetchone()
            assert row is not None
            figure_ids[f.ordinal] = str(row[0])

        async with conn.cursor() as cur:
            await cur.executemany(
                "insert into public.chunks (material_id, section_id, figure_id, ordinal, kind,"
                " heading_path, content, locations, embedding, embedding_model)"
                " values (%s, %s, %s, %s, %s, %s, %s, %s, %s::extensions.vector, %s)",
                [
                    (
                        material_id,
                        section_ids.get(c.section) if c.section is not None else None,
                        figure_ids.get(c.figure) if c.figure is not None else None,
                        c.ordinal,
                        c.kind,
                        c.heading_path,
                        c.content,
                        json.dumps(
                            [{"page": loc.page, "bbox": list(loc.bbox)} for loc in c.locations]
                        ),
                        _vector(e),
                        embedding_model,
                    )
                    for c, e in zip(chunks, embeddings, strict=True)
                ],
            )

        await conn.execute(
            "update public.materials set status = 'ready', error = null, page_count = %s"
            " where id = %s",
            (parsed.page_count, material_id),
        )
