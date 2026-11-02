"""Records the API's server errors in `public.api_errors`, for the operator's alerts (D99).

A row says where an error happened (method, route, exception type, file and line), never
its message, which can quote what a user sent; the full traceback is in the API's logs.
Recording never adds a failure of its own: if the database can't be reached, the error is
only logged.
"""

import logging
import re
import traceback
from typing import Any

from psycopg import AsyncConnection
from psycopg_pool import AsyncConnectionPool
from starlette.types import ASGIApp, Message, Receive, Scope, Send

logger = logging.getLogger(__name__)

Pool = AsyncConnectionPool[AsyncConnection[Any]]

# How long a request may wait for a connection to record its error.
RECORD_TIMEOUT = 2.0

_ID = re.compile(r"/(?:[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}|\d+)(?=/|$)")


def describe(exc: BaseException) -> str:
    """The exception's type and the innermost line of Engram's code it passed through, such as
    `KeyError at engram/chat/answer.py:88`."""
    frames = traceback.extract_tb(exc.__traceback__)
    ours = [f for f in frames if "/engram/" in f.filename]
    if not (ours or frames):
        return type(exc).__name__
    frame = (ours or frames)[-1]
    path = frame.filename
    path = "engram/" + path.rsplit("/engram/", 1)[1] if "/engram/" in path else path
    return f"{type(exc).__name__} at {path}:{frame.lineno}"


def route_of(scope: Scope) -> str:
    """The route's template (`/courses/{course_id}`), or the path with ids replaced."""
    route = scope.get("route")
    path = getattr(route, "path", None)
    if isinstance(path, str):
        return path
    return _ID.sub("/{id}", str(scope.get("path", "")))


async def record(pool: Pool, method: str, route: str, error: str, status: int | None) -> None:
    try:
        async with pool.connection(timeout=RECORD_TIMEOUT) as conn:
            await conn.execute(
                "insert into public.api_errors (method, route, status, error)"
                " values (%s, %s, %s, %s)",
                (method, route, status, error),
            )
    except Exception:
        logger.exception("couldn't record an API error (%s %s: %s)", method, route, error)


class RecordErrors:
    """ASGI middleware: records requests that raise, or answer with a 5xx status."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        status: int | None = None

        async def watch(message: Message) -> None:
            nonlocal status
            if message["type"] == "http.response.start":
                status = int(message["status"])
            await send(message)

        try:
            await self.app(scope, receive, watch)
        except Exception as exc:
            await self._record(scope, describe(exc), status or 500)
            raise
        if status is not None and status >= 500:
            await self._record(scope, f"HTTP {status}", status)

    async def _record(self, scope: Scope, error: str, status: int) -> None:
        pool: Pool | None = getattr(scope["app"].state, "pool", None)
        if pool is None:
            return
        await record(pool, scope["method"], route_of(scope), error, status)
