"""Admin command line: create courses and ingest textbooks.

    uv run engram-admin create-course --owner student@example.com --title "Biology 101"
    uv run engram-admin ingest path/to/book.pdf --course <course id>
    uv run engram-admin materials --course <course id>

Uses the database URL and Supabase secret key from the environment (see .env.example).
"""

import argparse
import asyncio
import sys
import uuid
from pathlib import Path
from typing import Any

from psycopg import AsyncConnection

from engram.config import get_settings
from engram.ingest.job import KIND as INGEST
from engram.storage import Storage, safe_filename
from engram.worker import queue

CONTENT_TYPES = {
    ".pdf": "application/pdf",
    ".pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
}


async def create_course(conn: AsyncConnection[Any], owner_email: str, title: str) -> str:
    cur = await conn.execute("select id from auth.users where email = %s", (owner_email,))
    row = await cur.fetchone()
    if row is None:
        raise SystemExit(f"No account for {owner_email}. Invite them first.")
    cur = await conn.execute(
        "insert into public.courses (owner_id, title) values (%s, %s) returning id",
        (row[0], title),
    )
    created = await cur.fetchone()
    assert created is not None
    return str(created[0])


async def ingest(
    conn: AsyncConnection[Any], storage: Storage, file: Path, course_id: str, kind: str, title: str
) -> str:
    content_type = CONTENT_TYPES.get(file.suffix.lower())
    if content_type is None:
        raise SystemExit(f"Unsupported file type: {file.suffix} (PDF or PowerPoint only)")
    material_id = str(uuid.uuid4())
    path = f"{course_id}/{material_id}/{safe_filename(file.name)}"
    await conn.execute(
        "insert into public.materials (id, course_id, kind, title, storage_path)"
        " values (%s, %s, %s, %s, %s)",
        (material_id, course_id, kind, title, path),
    )
    await storage.upload(path, await asyncio.to_thread(file.read_bytes), content_type)
    async with conn.transaction():
        await conn.execute(
            "update public.materials set status = 'queued' where id = %s", (material_id,)
        )
        await queue.enqueue(conn, INGEST, {"material_id": material_id})
    return material_id


async def list_materials(
    conn: AsyncConnection[Any], course_id: str | None
) -> list[tuple[Any, ...]]:
    cur = await conn.execute(
        "select m.id, c.title, m.kind::text, m.title, m.status::text, m.page_count, m.error"
        "  from public.materials m join public.courses c on c.id = m.course_id"
        " where %s::uuid is null or m.course_id = %s::uuid"
        " order by m.created_at",
        (course_id, course_id),
    )
    return await cur.fetchall()


async def _main(args: argparse.Namespace) -> None:
    settings = get_settings()
    async with await AsyncConnection.connect(settings.database_url, autocommit=True) as conn:
        if args.command == "create-course":
            print(await create_course(conn, args.owner, args.title))
        elif args.command == "ingest":
            async with Storage(settings) as storage:
                title = args.title or args.file.stem
                material_id = await ingest(conn, storage, args.file, args.course, args.kind, title)
            print(f"{material_id} queued; the worker will process it")
        elif args.command == "materials":
            for row in await list_materials(conn, args.course):
                print(" | ".join("" if v is None else str(v) for v in row))


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="engram-admin", description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("create-course", help="create a course owned by an existing account")
    p.add_argument("--owner", required=True, help="the owner's email")
    p.add_argument("--title", required=True)

    p = sub.add_parser("ingest", help="upload a textbook or slides and queue ingestion")
    p.add_argument("file", type=Path)
    p.add_argument("--course", required=True, help="course id")
    p.add_argument("--kind", choices=["textbook", "slides"], default="textbook")
    p.add_argument("--title", help="defaults to the file name")

    p = sub.add_parser("materials", help="list materials and their ingestion status")
    p.add_argument("--course", help="course id; all courses if omitted")

    args = parser.parse_args(argv)
    if args.command == "ingest" and not args.file.is_file():
        parser.error(f"no such file: {args.file}")
    asyncio.run(_main(args))


if __name__ == "__main__":
    main(sys.argv[1:])
