"""Hybrid retrieval over a course's chunks: vector similarity and full-text search, each
ranked separately and merged by reciprocal rank fusion.

Vectors find passages that mean the same thing in other words; keywords find exact terms
(names, jargon) that small embedding models blur. Fusing ranks rather than scores avoids
calibrating two incomparable scales. Queries run as the student, so RLS limits them to
materials they can read.
"""

from dataclasses import dataclass
from typing import Any
from uuid import UUID

from psycopg import AsyncConnection
from psycopg.rows import dict_row

# Candidates taken from each ranking, and passages given to the model.
CANDIDATES = 30
PASSAGES = 8
# The usual RRF constant: damps the difference between the very top ranks.
RRF_K = 60

_SEARCH = """
with q as (
  select %(embedding)s::extensions.vector as v,
         -- Any of the question's terms, not all of them: questions are phrased loosely.
         replace(plainto_tsquery('english', %(text)s)::text, '&', '|')::tsquery as t
),
scope as (
  select id from public.materials where course_id = %(course)s and status = 'ready'
),
vec as (
  select k.id, row_number() over (order by k.embedding <=> q.v) as rank
    from public.chunks k, q
   where k.material_id in (select id from scope) and k.embedding is not null
   order by k.embedding <=> q.v
   limit %(candidates)s
),
kw as (
  select k.id, row_number() over (order by ts_rank_cd(k.fts, q.t) desc) as rank
    from public.chunks k, q
   where k.material_id in (select id from scope) and k.fts @@ q.t
   order by ts_rank_cd(k.fts, q.t) desc
   limit %(candidates)s
),
fused as (
  select id, sum(1.0 / (%(rrf_k)s + rank)) as score
    from (select * from vec union all select * from kw) ranked
   group by id
)
select k.id, k.material_id, m.title as book, k.heading_path, k.content, k.locations
  from fused f
  join public.chunks k on k.id = f.id
  join public.materials m on m.id = k.material_id
 order by f.score desc
 limit %(passages)s
"""


@dataclass(frozen=True)
class Passage:
    chunk_id: UUID
    material_id: UUID
    book: str
    heading_path: list[str]
    text: str
    page: int | None

    @property
    def title(self) -> str:
        parts = [self.book, *self.heading_path[-1:]]
        if self.page is not None:
            parts.append(f"page {self.page}")
        return " · ".join(parts)


def body(content: str, heading_path: list[str]) -> str:
    """A chunk's text without the heading path it starts with."""
    return content.removeprefix(" > ".join(heading_path) + "\n\n")


async def search(
    db: AsyncConnection[Any], course_id: UUID, text: str, embedding: list[float]
) -> list[Passage]:
    async with db.cursor(row_factory=dict_row) as cur:
        await cur.execute(
            _SEARCH,
            {
                "course": course_id,
                "text": text,
                "embedding": str(embedding),
                "candidates": CANDIDATES,
                "rrf_k": RRF_K,
                "passages": PASSAGES,
            },
        )
        rows = await cur.fetchall()
    return [
        Passage(
            chunk_id=row["id"],
            material_id=row["material_id"],
            book=row["book"],
            heading_path=row["heading_path"],
            text=body(row["content"], row["heading_path"]),
            page=row["locations"][0]["page"] if row["locations"] else None,
        )
        for row in rows
    ]
