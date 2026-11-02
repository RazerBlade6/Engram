import json
import uuid
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any

import psycopg
import pytest
from psycopg import AsyncConnection
from pydantic import BaseModel

from engram.config import Settings
from engram.ingest import job as ingest_job
from engram.ingest.describe import FigureDescription
from engram.ingest.failures import Unreadable
from engram.ingest.model import Chunk, Figure, Location, ParsedMaterial, Section
from engram.llm import ProviderError, Router, Usage
from engram.worker import main, queue
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
            # A different image: the same one would share its description (D96).
            Figure(1, Location(4, (0, 0, 100, 100)), PNG + b"\0", None, 2, ["Chapter 2 Genetics"]),
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
        self.calls = 0

    async def structured(
        self,
        model: str,
        *,
        system: str,
        parts: list[Any],
        schema: type[BaseModel],
        max_tokens: int = 4096,
        usage: Usage | None = None,
    ) -> Any:
        prompt = parts[-1].text
        self.calls += 1
        if usage is not None:
            usage.add(Usage(1, 100, 10, models={model}))
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


@pytest.fixture(autouse=True)
def no_reused_descriptions(database_url: str) -> Iterator[None]:
    """Each test describes its figures afresh: the test images are all alike."""

    def forget() -> None:
        with psycopg.connect(database_url, autocommit=True) as c:
            c.execute("delete from public.figure_descriptions where model like 'fake:%'")

    forget()
    yield
    forget()


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


def read_again(database_url: str, material_id: str) -> None:
    """Queue a ready material to be read again, as an admin would; a job that simply runs
    again leaves a ready material alone (D91)."""
    with psycopg.connect(database_url, autocommit=True) as c:
        c.execute("update public.materials set status = 'queued' where id = %s", (material_id,))


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
    read_again(database_url, material["id"])
    await handler(settings, storage, lambda p, s: smaller)(job)
    assert rows(
        database_url, "select count(*) from public.figures where material_id = %s", material["id"]
    ) == [(1,)]
    assert rows(
        database_url, "select count(*) from public.chunks where material_id = %s", material["id"]
    ) == [(4,)]
    assert len(storage.objects) == 1


async def test_reingesting_keeps_coverage_of_matching_sections(
    database_url: str, material: dict[str, str]
) -> None:
    settings = Settings(database_url=database_url)
    job = Job(1, ingest_job.KIND, {"material_id": material["id"]}, 1, 3)
    await handler(settings, FakeStorage(), lambda p, s: parsed_material())(job)
    with psycopg.connect(database_url, autocommit=True) as c:
        c.execute(
            "insert into public.covered_sections (section_id, covered_by)"
            " select id, %s from public.sections where material_id = %s",
            (material["owner"], material["id"]),
        )

    # Chapter 2 is renamed by the new parse, so its mark has nothing to attach to.
    reparsed = parsed_material()
    reparsed.sections[2] = Section(2, 1, "Chapter 2 Heredity", 4, 4)
    read_again(database_url, material["id"])
    await handler(settings, FakeStorage(), lambda p, s: reparsed)(job)

    covered = rows(
        database_url,
        "select s.title, c.covered_by::text from public.covered_sections c"
        " join public.sections s on s.id = c.section_id"
        " where s.material_id = %s order by s.ordinal",
        material["id"],
    )
    assert covered == [("Chapter 1 Cells", material["owner"]), ("1.1 Structure", material["owner"])]


async def test_reingesting_keeps_cards_with_their_chapter(
    database_url: str, material: dict[str, str]
) -> None:
    settings = Settings(database_url=database_url)
    job = Job(1, ingest_job.KIND, {"material_id": material["id"]}, 1, 3)
    await handler(settings, FakeStorage(), lambda p, s: parsed_material())(job)
    with psycopg.connect(database_url, autocommit=True) as c:
        c.execute(
            "insert into public.cards (material_id, section_id, ordinal, kind, concept, prompt,"
            " answer, sources, generated_by, prompt_version)"
            " select material_id, id, 0, 'basic', 'c', 'Q', 'A', %s, 'm', 'v'"
            " from public.sections where material_id = %s and level = 1",
            ('[{"quote": "q", "locations": []}]', material["id"]),
        )

    reparsed = parsed_material()
    reparsed.sections[2] = Section(2, 1, "Chapter 2 Heredity", 4, 4)
    read_again(database_url, material["id"])
    await handler(settings, FakeStorage(), lambda p, s: reparsed)(job)

    cards = rows(
        database_url,
        "select s.title from public.cards k left join public.sections s on s.id = k.section_id"
        " where k.material_id = %s order by s.title nulls last",
        material["id"],
    )
    # Chapter 2 was renamed: its card is kept, waiting for a chapter to belong to.
    assert cards == [("Chapter 1 Cells",), (None,)]


async def test_a_ready_material_is_not_read_again(
    database_url: str, material: dict[str, str]
) -> None:
    settings = Settings(database_url=database_url)
    job = Job(1, ingest_job.KIND, {"material_id": material["id"]}, 1, 3)
    await handler(settings, FakeStorage(), lambda p, s: parsed_material())(job)
    before = rows(
        database_url, "select id from public.chunks where material_id = %s", material["id"]
    )
    parses = []

    def parser(path: Path, slides: bool) -> ParsedMaterial:
        parses.append(path)
        return parsed_material()

    # The same job again, as after a lost connection just as the first run finished.
    await handler(settings, FakeStorage(), parser)(job)
    assert parses == []
    assert (
        rows(database_url, "select id from public.chunks where material_id = %s", material["id"])
        == before
    )
    assert rows(
        database_url, "select status::text from public.materials where id = %s", material["id"]
    ) == [("ready",)]


async def test_figures_already_described_are_not_paid_for_again(
    database_url: str, material: dict[str, str], make_user: Callable[..., str]
) -> None:
    """D96: the same file uploaded again, here to another course, reuses its descriptions."""
    settings = Settings(database_url=database_url)
    first = FakeProvider()
    job = Job(1, ingest_job.KIND, {"material_id": material["id"]}, 1, 3)
    await handler(settings, FakeStorage(), lambda p, s: parsed_material(), first)(job)
    assert first.calls == 2

    again = FakeProvider()
    with psycopg.connect(database_url, autocommit=True) as c:
        course = c.execute(
            "insert into public.courses (owner_id, title) values (%s, 'Bio') returning id",
            (make_user(),),
        ).fetchone()
        assert course
        other = str(uuid.uuid4())
        c.execute(
            "insert into public.materials (id, course_id, kind, title, storage_path, status)"
            " values (%s, %s, 'textbook', 'Biology', %s, 'queued')",
            (other, course[0], f"{course[0]}/{other}/biology.pdf"),
        )
    job = Job(2, ingest_job.KIND, {"material_id": other}, 1, 3)
    await handler(settings, FakeStorage(), lambda p, s: parsed_material(), again)(job)
    assert again.calls == 0
    assert (
        rows(
            database_url,
            "select description, labels from public.figures where material_id = %s order by ordinal",
            other,
        )
        == [("A cell with a nucleus.", ["Nucleus", "Membrane"])] * 2
    )
    # Nothing was paid for, so nothing is recorded as spent.
    assert rows(
        database_url, "select count(*) from public.llm_usage where material_id = %s", other
    ) == [(0,)]


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
    # Both figures were sent, the declined one included: both are billed.
    assert rows(
        database_url,
        "select job, model, requests from public.llm_usage where material_id = %s",
        material["id"],
    ) == [("describe_figures", "vision-1", 2)]
    [content] = rows(
        database_url,
        "select content from public.chunks where material_id = %s"
        " and kind = 'figure' order by ordinal limit 1",
        material["id"],
    )[0]
    assert content.endswith("Figure 1.1 A cell.")


async def test_a_failed_attempt_reraises_and_leaves_the_material_reading(
    database_url: str, material: dict[str, str]
) -> None:
    def broken(path: Path, slides: bool) -> ParsedMaterial:
        raise ValueError("corrupt PDF")

    with pytest.raises(ValueError):
        await handler(Settings(database_url=database_url), FakeStorage(), broken)(
            Job(1, ingest_job.KIND, {"material_id": material["id"]}, 1, 3)
        )
    # The job may be retried; only its final failure marks the material failed.
    assert rows(
        database_url, "select status::text from public.materials where id = %s", material["id"]
    ) == [("processing",)]


async def test_the_job_failing_for_good_marks_the_material_failed(
    database_url: str, material: dict[str, str]
) -> None:
    async with await AsyncConnection.connect(database_url, autocommit=True) as conn:
        job = await queue.enqueue(conn, ingest_job.KIND, {"material_id": material["id"]})
        try:
            claimed = Job(job, ingest_job.KIND, {"material_id": material["id"]}, 1, 3)
            await conn.execute(
                "update public.jobs set status = 'running', locked_by = 'w' where id = %s", (job,)
            )
            await queue.fail(conn, claimed, "w", "ValueError: corrupt PDF")
            assert rows(
                database_url,
                "select status::text from public.materials where id = %s",
                material["id"],
            ) == [("queued",)]

            await conn.execute(
                "update public.jobs set status = 'running', locked_by = 'w' where id = %s", (job,)
            )
            await queue.fail(conn, claimed, "w", "ValueError: corrupt PDF", permanent=True)
            assert rows(
                database_url,
                "select status::text, error from public.materials where id = %s",
                material["id"],
            ) == [("failed", "ValueError: corrupt PDF")]
        finally:
            await conn.execute("delete from public.jobs where id = %s", (job,))


async def fail_for_good(database_url: str, material_id: str, error: str) -> None:
    """Fail the material's job permanently, as the worker does."""
    async with await AsyncConnection.connect(database_url, autocommit=True) as conn:
        job = await queue.enqueue(conn, ingest_job.KIND, {"material_id": material_id})
        try:
            await conn.execute(
                "update public.jobs set status = 'running', locked_by = 'w' where id = %s", (job,)
            )
            claimed = Job(job, ingest_job.KIND, {"material_id": material_id}, 1, 3)
            await queue.fail(conn, claimed, "w", error, permanent=True)
        finally:
            await conn.execute("delete from public.jobs where id = %s", (job,))


def failure(database_url: str, material_id: str) -> list[tuple[Any, ...]]:
    return rows(
        database_url,
        "select status::text, failure::text from public.materials where id = %s",
        material_id,
    )


async def test_the_material_shows_each_stage_while_it_is_read(
    database_url: str, material: dict[str, str]
) -> None:
    def stage() -> Any:
        return rows(
            database_url, "select stage::text from public.materials where id = %s", material["id"]
        )[0][0]

    seen: list[Any] = []

    def parser(path: Path, slides: bool) -> ParsedMaterial:
        seen.append(stage())
        return parsed_material()

    class Watching(FakeProvider):
        async def structured(self, model: str, **kwargs: Any) -> Any:
            seen.append(stage())
            return await super().structured(model, **kwargs)

    class Embedding(FakeEmbedder):
        def passages(self, texts: list[str]) -> list[list[float]]:
            seen.append(stage())
            return super().passages(texts)

    await ingest_job.make_handler(
        Settings(database_url=database_url),
        router=Router(Settings(model_figure_description="fake:vision-1"), {"fake": Watching()}),
        storage=FakeStorage(),  # type: ignore[arg-type]
        embedder=Embedding(),  # type: ignore[arg-type]
        parser=parser,
    )(Job(1, ingest_job.KIND, {"material_id": material["id"]}, 1, 3))
    assert seen == ["parsing", "describing", "describing", "indexing"]
    assert stage() is None


async def test_an_unreadable_file_keeps_its_reason(
    database_url: str, material: dict[str, str]
) -> None:
    def locked(path: Path, slides: bool) -> ParsedMaterial:
        raise Unreadable("protected", "Incorrect password error")

    with pytest.raises(Unreadable):
        await handler(Settings(database_url=database_url), FakeStorage(), locked)(
            Job(1, ingest_job.KIND, {"material_id": material["id"]}, 1, 3)
        )
    await fail_for_good(database_url, material["id"], "Unreadable: Incorrect password error")
    assert failure(database_url, material["id"]) == [("failed", "protected")]


async def test_a_file_with_nothing_in_it_has_no_text(
    database_url: str, material: dict[str, str]
) -> None:
    def blank(path: Path, slides: bool) -> ParsedMaterial:
        return ParsedMaterial(page_count=2, sections=[], figures=[], chunks=[])

    with pytest.raises(Unreadable) as raised:
        await handler(Settings(database_url=database_url), FakeStorage(), blank)(
            Job(1, ingest_job.KIND, {"material_id": material["id"]}, 1, 3)
        )
    assert raised.value.reason == "no_text"


async def test_other_failures_are_unknown_or_stalled(
    database_url: str, material: dict[str, str], make_user: Callable[..., str]
) -> None:
    await fail_for_good(database_url, material["id"], "ValueError: boom")
    assert failure(database_url, material["id"]) == [("failed", "unknown")]

    with psycopg.connect(database_url, autocommit=True) as c:
        c.execute(
            "update public.materials set status = 'processing', failure = null where id = %s",
            (material["id"],),
        )
    await fail_for_good(database_url, material["id"], queue.GAVE_UP)
    assert failure(database_url, material["id"]) == [("failed", "stalled")]

    # Reading that ran past its time limit (D92) took too long too.
    with psycopg.connect(database_url, autocommit=True) as c:
        c.execute(
            "update public.materials set status = 'processing', failure = null where id = %s",
            (material["id"],),
        )
    timed_out = f"TimedOut: {main.TimedOut('ran longer than its limit of 2:30:00')}"
    await fail_for_good(database_url, material["id"], timed_out)
    assert failure(database_url, material["id"]) == [("failed", "stalled")]


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


async def test_usage_is_kept_when_the_material_was_deleted_meanwhile(
    database_url: str, material: dict[str, str]
) -> None:
    from engram.usage import record

    with psycopg.connect(database_url, autocommit=True) as c:
        c.execute("delete from public.materials where id = %s", (material["id"],))
    async with await psycopg.AsyncConnection.connect(database_url, autocommit=True) as conn:
        await record(
            conn,
            "describe_figures",
            Usage(3, 100, 10, models={"vision-1"}),
            material_id=material["id"],
        )
    assert rows(
        database_url,
        "select material_id, requests from public.llm_usage where job = 'describe_figures'"
        " order by id desc limit 1",
    ) == [(None, 3)]
