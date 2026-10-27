"""Database access for request handlers.

`UserDb` is a connection inside a transaction running as the `authenticated` role with the
caller's JWT claims, so row-level security decides what the request can see and change.
`ServiceDb` is a privileged connection for the few operations no user may do directly,
such as enqueueing jobs.
"""

import json
from collections.abc import AsyncIterator
from typing import Annotated, Any

from fastapi import Depends, Request
from psycopg import AsyncConnection
from psycopg_pool import AsyncConnectionPool

from engram.api.auth import CurrentUser


def get_pool(request: Request) -> AsyncConnectionPool[AsyncConnection[Any]]:
    pool: AsyncConnectionPool[AsyncConnection[Any]] = request.app.state.pool
    return pool


Pool = Annotated[AsyncConnectionPool[AsyncConnection[Any]], Depends(get_pool)]


async def user_db(pool: Pool, user: CurrentUser) -> AsyncIterator[AsyncConnection[Any]]:
    async with pool.connection() as conn, conn.transaction():
        await conn.execute("set local role authenticated")
        await conn.execute(
            "select set_config('request.jwt.claims', %s, true)", (json.dumps(user.claims),)
        )
        yield conn


async def service_db(pool: Pool) -> AsyncIterator[AsyncConnection[Any]]:
    async with pool.connection() as conn, conn.transaction():
        yield conn


UserDb = Annotated[AsyncConnection[Any], Depends(user_db)]
# For streaming responses: the transaction ends when the handler returns rather than when
# the response finishes, so a long stream doesn't hold a connection.
UserDbUntilStreaming = Annotated[AsyncConnection[Any], Depends(user_db, scope="function")]
ServiceDb = Annotated[AsyncConnection[Any], Depends(service_db)]
