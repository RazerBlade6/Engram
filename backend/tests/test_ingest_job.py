import json
import uuid
from collections.abc import Callable
from pathlib import Path
from typing import Any

import psycopg
import pytest
from pydantic import BaseModel

from engram.config import Settings
from engram.ingest import job as ingest_job
from engram.ingest.describe import FigureDescription
from engram.ingest.model import Chunk, Figure, Location, ParsedMaterial, Section
from engram.llm import ProviderError, Router
from engram.worker.queue import Job

PNG = b"\x89PNG fake"


def parsed_material() -> ParsedMaterial:
    here = Location(1, (10.0, 20.0, 300.0, 400.0))
    return ParsedMaterial(
        page_count=4,
        sections=[
            Section(0, 1, "Chapter 1 Cells", 1, 3),
            Section(1, 2, "1.1 Structure", 1, 2, parent=0),
            Section(2, 1, "Chapter 2 Genetics", 4, 4),
        ],
        figures=[
            Figure(0, here, PNG, "Figure 1.1 A cell.", 1, ["Chapter 1 Cells", "1.1 Structure"]),
            Figure(1, Location(4, (0, 0, 100, 100)), PNG, None, 2, ["Chapter 2 Genetics"]),
        ],
        chunks=[
            Chunk(0, "text", "Cells are small.", ["Chapter 1 Cells"], [here], 0),
            Chunk(
                1,
                "text",
                "The nucleus stores DNA.",
                ["Chapter 1 Cells", "1.1 Structure"],
                [here],
                1,
            ),
            Chunk(2, "table", "| a | b |", ["Chapter 2 Genetics"], [Location(4, (1, 2, 3, 4))], 2),
        ],
    )


class FakeProvider:
    name = "fake"

    def __init__(self, decline: set[str] | None = None) -> None:
        self.decline = decline or set()

    async def structured(
        self, model: str, *, system: str, parts: list[Any], schema: type[BaseModel]
    ) -> Any:
        prompt = parts[-1].text
        if any(word in prompt for word in self.decline):
            raise ProviderError("declined")
        return FigureDescription(
            kind="diagram", description="A cell with a nucleus.", labels=["Nucleus", "Membrane"]
        )


class FakeStorage:
    def __init__(self) -> None:
        self.objects: dict[str, bytes] = {}

    async def download(self, path: str) -> bytes:
        return b"%PDF fake"

    async def upload(self, path: str, data: bytes, content_type: str) -> None:
        self.objects[path] = data

    async def remove_prefix(self, prefix: str) -> None:
        for key in [k for k in self.objects if k.startswith(prefix + "/")]:
            del self.objects[key]


class FakeEmbedder:
    model_name = "fake-embedder"

    def passages(self, texts: list[str]) -> list[list[float]]:
        return [[(i + 1) / 1000] * 384 for i, _ in enumerate(texts)]


@pytest.fixture
def material(database_url: str, make_user: Callable[..., str]) -> dict[str, str]:
    owner = make_user()
    with psycopg.connect(database_url, autocommit=True) as c:
        course = c.execute(
            "insert into public.courses (owner_id, title) values (%s, 'Bio') returning id", (owner,)
        ).fetchone()
        assert course
        material_id = str(uuid.uuid4())
        c.execute(
            "insert into public.materials (id, course_id, kind, title, storage_path, status)"
            " values (%s, %s, 'textbook', 'Biology', %s, 'queued')",
            (material_id, course[0], f"{course[0]}/{material_id}/biology.pdf"),
        )
    return {"id": material_id, "course": str(course[0]), "owner": owner}


def handler(
    settings: Settings,
    storage: FakeStorage,
    parser: Callable[[Path, bool], ParsedMaterial],
    provider: FakeProvider | None = None,
) -> Any:
    router = Router(
        Settings(model_figure_description="fake:vision-1"), {"fake": provider or FakeProvider()}
    )
    return ingest_job.make_handler(
        settings,
        router=router,
        storage=storage,
        embedder=FakeEmbedder(),
        parser=parser,  # type: ignore[arg-type]
    )


def rows(database_url: str, sql: str, *params: Any) -> list[tuple[Any, ...]]:
    with psycopg.connect(database_url) as c:
        return c.execute(sql, params).fetchall()


async def test_ingest_stores_sections_figures_and_chunks(
    database_url: str, material: dict[str, str]
) -> None:
    storage = FakeStorage()
    settings = Settings(database_url=database_url)
    await handler(settings, storage, lambda p, s: parsed_material())(
        Job(1, ingest_job.KIND, {"material_id": material["id"]}, 1, 3)
    )

    assert rows(
        database_url,
        "select status::text, page_count, error from public.materials where id = %s",
        material["id"],
    ) == [("ready", 4, None)]

    sections = rows(
        database_url,
        "select s.title, p.title from public.sections s"
        " left join public.sections p on p.id = s.parent_id"
        " where s.material_id = %s order by s.ordinal",
        material["id"],
    )
    assert sections == [
        ("Chapter 1 Cells", None),
        ("1.1 Structure", "Chapter 1 Cells"),
        ("Chapter 2 Genetics", None),
    ]

    figures = rows(
        database_url,
        "select f.ordinal, s.title, f.description, f.labels, f.described_by,"
        " f.storage_path from public.figures f join public.sections s on s.id = f.section_id"
        " where f.material_id = %s order by f.ordinal",
        material["id"],
    )
    prefix = f"{material['course']}/{material['id']}/figures"
    assert figures[0] == (
        0,
        "1.1 Structure",
        "A cell with a nucleus.",
        ["Nucleus", "Membrane"],
        "fake:vision-1",
        f"{prefix}/0.png",
    )
    assert set(storage.objects) == {f"{prefix}/0.png", f"{prefix}/1.png"}

    chunks = rows(
        database_url,
        "select ordinal, kind::text, content, locations, embedding_model,"
        " vector_dims(embedding), figure_id is not null from public.chunks"
        " where material_id = %s order by ordinal",
        material["id"],
    )
    assert [c[1] for c in chunks] == ["text", "text", "table", "figure", "figure"]
    assert chunks[1][2] == "Chapter 1 Cells > 1.1 Structure\n\nThe nucleus stores DNA."
    assert chunks[0][3] == [{"page": 1, "bbox": [10.0, 20.0, 300.0, 400.0]}]
    assert "Labels: Nucleus, Membrane" in chunks[3][2] and "Figure 1.1 A cell." in chunks[3][2]
    assert all(c[4] == "fake-embedder" and c[5] == 384 for c in chunks)
    assert [c[6] for c in chunks] == [False, False, False, True, True]

    # Full-text search works on the stored content.
    assert rows(
        database_url,
        "select count(*) from public.chunks where material_id = %s"
        " and fts @@ plainto_tsquery('english', 'nucleus DNA')",
        material["id"],
    ) == [(1,)]


async def test_reingesting_replaces_previous_rows(
    database_url: str, material: dict[str, str]
) -> None:
    storage = FakeStorage()
    settings = Settings(database_url=database_url)
    job = Job(1, ingest_job.KIND, {"material_id": material["id"]}, 1, 3)
    await handler(settings, storage, lambda p, s: parsed_material())(job)
    smaller = parsed_material()
    smaller.figures = smaller.figures[:1]
    await handler(settings, storage, lambda p, s: smaller)(job)
    assert rows(
        database_url, "select count(*) from public.figures where material_id = %s", material["id"]
    ) == [(1,)]
    assert rows(
        database_url, "select count(*) from public.chunks where material_id = %s", material["id"]
    ) == [(4,)]
    assert len(storage.objects) == 1


async def test_declined_figure_keeps_its_caption(
    database_url: str, material: dict[str, str]
) -> None:
    await handler(
        Settings(database_url=database_url),
        FakeStorage(),
        lambda p, s: parsed_material(),
        FakeProvider(decline={"A cell."}),
    )(Job(1, ingest_job.KIND, {"material_id": material["id"]}, 1, 3))
    figures = rows(
        database_url,
        "select description, labels, described_by from public.figures"
        " where material_id = %s order by ordinal",
        material["id"],
    )
    assert figures[0] == (None, [], None)
    assert figures[1][0] == "A cell with a nucleus."
    [content] = rows(
        database_url,
        "select content from public.chunks where material_id = %s"
        " and kind = 'figure' order by ordinal limit 1",
        material["id"],
    )[0]
    assert content.endswith("Figure 1.1 A cell.")


async def test_failure_marks_material_failed_and_reraises(
    database_url: str, material: dict[str, str]
) -> None:
    def broken(path: Path, slides: bool) -> ParsedMaterial:
        raise ValueError("corrupt PDF")

    with pytest.raises(ValueError):
        await handler(Settings(database_url=database_url), FakeStorage(), broken)(
            Job(1, ingest_job.KIND, {"material_id": material["id"]}, 1, 3)
        )
    assert rows(
        database_url,
        "select status::text, error from public.materials where id = %s",
        material["id"],
    ) == [("failed", "ValueError: corrupt PDF")]


async def test_parsed_content_follows_course_access(
    database_url: str, material: dict[str, str], make_user: Callable[..., str]
) -> None:
    await handler(
        Settings(database_url=database_url), FakeStorage(), lambda p, s: parsed_material()
    )(Job(1, ingest_job.KIND, {"material_id": material["id"]}, 1, 3))
    stranger = make_user()

    def visible(user: str) -> tuple[int, ...]:
        with psycopg.connect(database_url) as c:
            c.execute("set local role authenticated")
            c.execute(
                "select set_config('request.jwt.claims', %s, true)",
                (json.dumps({"sub": user, "role": "authenticated"}),),
            )
            row = c.execute(
                "select (select count(*) from public.sections), (select count(*) from"
                " public.figures), (select count(*) from public.chunks)"
            ).fetchone()
            assert row
            return tuple(row)

    assert visible(material["owner"]) == (3, 2, 5)
    assert visible(stranger) == (0, 0, 0)
