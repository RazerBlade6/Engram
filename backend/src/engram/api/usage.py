"""Usage events, logged only for people who agreed (see the usage events migration).

Events come from two places. Handlers log what they do (a rating, a flag, an upload) with
`log`, in the request's transaction, so an event exists only if the change does. The
browser reports what only it sees (page views, how long an answer took to start) through
`POST /events`. Neither holds text a student wrote or read.
"""

import json
from functools import partial
from typing import Annotated, Any, Literal
from uuid import UUID

from fastapi import Depends, Header
from psycopg import AsyncConnection
from psycopg.types.json import Jsonb

Event = Literal[
    # From handlers
    "review",
    "flag",
    "unflag",
    "course_created",
    "chapter_covered",
    "chapter_unmarked",
    "material_uploaded",
    "material_deleted",
    "date_added",
    "date_changed",
    "date_deleted",
    # From the browser
    "session_start",
    "page_view",
    "source_opened",
    "chat_question",
]


def get_visit(x_session: Annotated[str | None, Header()] = None) -> UUID | None:
    """The browser's visit id: one per tab, renewed after half an hour idle."""
    try:
        return UUID(x_session) if x_session else None
    except ValueError:
        return None


Visit = Annotated[UUID | None, Depends(get_visit)]

_dumps = partial(json.dumps, default=str)


async def log(db: AsyncConnection[Any], visit: UUID | None, name: Event, **data: Any) -> None:
    """Record an event for the current user, if they agreed to logging; otherwise nothing."""
    await db.execute(
        "insert into public.usage_events (session_id, name, data)"
        " select %s, %s, %s where public.logs_usage()",
        (visit, name, Jsonb(data, dumps=_dumps)),
    )


async def logs_usage(db: AsyncConnection[Any]) -> bool:
    cur = await db.execute("select public.logs_usage()")
    row = await cur.fetchone()
    return bool(row and row[0])
