"""Shared fixtures.

Database tests run against the local Supabase stack (`supabase start`). Locally they are
skipped if it isn't running; CI sets ENGRAM_REQUIRE_DB=1 so a missing database fails loudly.
"""

import os
import uuid
from collections.abc import AsyncIterator, Iterator
from typing import Any

import psycopg
import pytest
from psycopg import AsyncConnection

from engram.config import get_settings


@pytest.fixture(scope="session")
def database_url() -> str:
    url = get_settings().database_url
    try:
        psycopg.connect(url, connect_timeout=2).close()
    except psycopg.OperationalError as exc:
        if os.environ.get("ENGRAM_REQUIRE_DB") == "1":
            raise
        pytest.skip(f"database not reachable ({exc.__class__.__name__}); run `supabase start`")
    return url


@pytest.fixture
async def conn(database_url: str) -> AsyncIterator[AsyncConnection[Any]]:
    """A connection whose work is rolled back after the test."""
    async with await AsyncConnection.connect(database_url) as c:
        yield c
        await c.rollback()


@pytest.fixture
def make_user(database_url: str) -> Iterator[Any]:
    """Creates auth users (and, via trigger, profiles); deletes them afterwards."""
    created: list[str] = []

    def make(role: str = "student") -> str:
        user_id = str(uuid.uuid4())
        with psycopg.connect(database_url, autocommit=True) as c:
            c.execute(
                "insert into auth.users (id, aud, role, email, raw_user_meta_data)"
                " values (%s, 'authenticated', 'authenticated', %s, '{}')",
                (user_id, f"{user_id}@test.invalid"),
            )
            c.execute("update public.profiles set role = %s where id = %s", (role, user_id))
        created.append(user_id)
        return user_id

    yield make
    with psycopg.connect(database_url, autocommit=True) as c:
        c.execute("delete from auth.users where id = any(%s::uuid[])", (created,))
