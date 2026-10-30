"""Records what each model-calling job cost, in tokens (see the llm_usage migration)."""

import logging
from typing import Any

from psycopg import AsyncConnection

from engram.llm import Usage

logger = logging.getLogger(__name__)


async def record(
    conn: AsyncConnection[Any],
    job: str,
    usage: Usage,
    *,
    material_id: str | None = None,
    section_id: str | None = None,
) -> None:
    if usage.requests == 0:
        return
    logger.info(
        "%s used %s requests, %s input and %s output tokens on %s",
        job,
        usage.requests,
        usage.input_tokens,
        usage.output_tokens,
        ", ".join(sorted(usage.models)),
    )
    await conn.execute(
        "insert into public.llm_usage (job, model, material_id, section_id, requests,"
        " input_tokens, output_tokens, cache_read_input_tokens, cache_creation_input_tokens)"
        # A material or section deleted while the job ran is recorded as null: still billed.
        " values (%s, %s, (select id from public.materials where id = %s),"
        " (select id from public.sections where id = %s), %s, %s, %s, %s, %s)",
        (
            job,
            ", ".join(sorted(usage.models)),
            material_id,
            section_id,
            usage.requests,
            usage.input_tokens,
            usage.output_tokens,
            usage.cache_read_input_tokens,
            usage.cache_creation_input_tokens,
        ),
    )
