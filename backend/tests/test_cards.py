import json
import uuid
from collections.abc import Callable, Iterator
from typing import Any

import psycopg
import pytest
from fastapi.testclient import TestClient
from pydantic import BaseModel

from engram.api.auth import get_verifier
from engram.api.main import create_app
from engram.cards import job as cards_job
from engram.cards.generate import (
    Card,
    CardSet,
    GeneratedCard,
    Passage,
    Source,
    accept,
    batches,
    distinct,
)
from engram.config import Settings
from engram.llm import ProviderError, ProviderUnavailable, Router, Usage
from engram.worker.queue import Job
from tests.test_api import FakeVerifier, auth, token_for

HERE = [{"page": 3, "bbox": [1, 2, 3, 4]}]


def passage(content: str, group: str = "g1", chunk_id: str = "c1") -> Passage:
    return Passage(chunk_id, group, "text", ["Chapter 1 Cells"], content, HERE)


def card(kind: str = "basic", **fields: Any) -> GeneratedCard:
    values: dict[str, Any] = {
        "kind": kind,
        "concept": "Nucleus",
        "prompt": "What does the nucleus store?",
        "answer": "DNA",
        "distractors": [],
        "sources": [Source(passage=1, quote="The nucleus stores DNA.")],
    }
    return GeneratedCard(**(values | fields))


# Grounding and format checks ------------------------------------------------------------

BATCH = [passage("Chapter 1 Cells\n\nThe nucleus   stores DNA. Ribosomes make proteins.")]


def test_a_card_is_kept_with_its_source_location() -> None:
    [kept], dropped = accept([card()], BATCH)
    assert dropped == {}
    assert (kept.prompt, kept.answer) == ("What does the nucleus store?", "DNA")
    assert kept.sources == [
        {
            "chunk_id": "c1",
            "quote": "The nucleus stores DNA.",
            "heading_path": ["Chapter 1 Cells"],
            "locations": HERE,
        }
    ]


def test_quotes_match_despite_spacing_case_and_punctuation() -> None:
    quote = Source(passage=1, quote="the nucleus stores DNA ribosomes make proteins")
    assert accept([card(sources=[quote])], BATCH)[0]


def test_cards_the_passages_do_not_support_are_dropped() -> None:
    invented = card(sources=[Source(passage=1, quote="The nucleus is the cell's brain.")])
    missing = card(prompt="Q2", sources=[Source(passage=7, quote="The nucleus stores DNA.")])
    tiny = card(prompt="Q3", sources=[Source(passage=1, quote="DNA")])
    assert accept([invented, missing, tiny], BATCH) == ([], {"unsupported": 3})


def test_cloze_needs_exactly_one_hidden_span_and_answers_with_it() -> None:
    good = card("cloze", prompt="The nucleus stores {{DNA}}.", answer="dna!")
    none = card("cloze", prompt="The nucleus stores DNA.")
    two = card("cloze", prompt="The {{nucleus}} stores {{DNA}}.")
    kept, dropped = accept([good, none, two], BATCH)
    assert [(c.prompt, c.answer) for c in kept] == [("The nucleus stores {{DNA}}.", "DNA")]
    assert dropped == {"cloze format": 2}


def test_multiple_choice_needs_three_distinct_distractors() -> None:
    good = card("mcq", distractors=["RNA", "Proteins", "Lipids"])
    short = card("mcq", prompt="Q2", distractors=["RNA", "Proteins"])
    repeated = card("mcq", prompt="Q3", distractors=["RNA", "dna", "Lipids"])
    kept, dropped = accept([good, short, repeated], BATCH)
    [mcq] = kept
    assert sorted(mcq.choices) == ["DNA", "Lipids", "Proteins", "RNA"]
    assert accept([good], BATCH)[0][0].choices == mcq.choices  # same order every time
    assert dropped == {"mcq choices": 2}


def test_repeated_cards_are_dropped_across_the_chapter() -> None:
    def kept(kind: str, prompt: str, answer: str) -> Card:
        return Card(kind, "c", prompt, answer, [], [{"chunk_id": "c1"}])

    first = kept(
        "cloze", "The two hemispheres are joined by the {{corpus callosum}}.", "corpus callosum"
    )
    cards = [
        first,
        kept("cloze", "The {{corpus callosum}} joins the two hemispheres.", "Corpus callosum"),
        # The same sentence as a different kind of card.
        kept("basic", "The two hemispheres are joined by the corpus callosum.", "True"),
        # Same answer, a different fact: kept.
        kept("mcq", "Which structure is cut in split-brain surgery?", "Corpus callosum"),
    ]
    assert distinct(cards) == ([first, cards[3]], 2)


def test_batches_keep_subsections_together_unless_too_large() -> None:
    words = " ".join(["word"] * 40)
    a1, a2 = passage(words, "a", "a1"), passage(words, "a", "a2")
    b1 = passage(words, "b", "b1")
    c = [passage(words, "c", f"c{i}") for i in range(3)]
    assert batches([a1, a2, b1], budget=100) == [[a1, a2], [b1]]
    assert batches([a1, a2, b1], budget=200) == [[a1, a2, b1]]
    assert batches(c, budget=100) == [c[:2], c[2:]]


# The job ------------------------------------------------------------------------------


class FakeProvider:
    """Makes one card per text passage, citing it. `during` runs inside each call."""

    name = "fake"

    def __init__(
        self, during: Callable[[], None] | None = None, fail: Exception | None = None
    ) -> None:
        self.prompts: list[str] = []
        self.during = during
        self.fail = fail

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
        if usage is not None:
            usage.add(Usage(1, 100, 10, models={model}))
        self.prompts.append(prompt)
        if self.during:
            self.during()
        if self.fail:
            raise self.fail
        cards = []
        for block in prompt.split("\n\n[P")[1:]:
            number, _, rest = block.partition("]")
            text = rest.split("\n", 1)[1]
            cards.append(
                GeneratedCard(
                    kind="basic",
                    concept="c",
                    prompt=f"What does passage {number} say?",
                    answer=text,
                    distractors=[],
                    sources=[Source(passage=int(number), quote=text)],
                )
            )
        return CardSet(cards=cards)


@pytest.fixture
def chapter(database_url: str, make_user: Callable[..., str]) -> Iterator[dict[str, str]]:
    """A textbook chapter with two subsections and end-of-chapter questions. Marking it covered
    queues a real job; those are removed afterwards so the worker tests can't claim them."""
    owner = make_user()
    with psycopg.connect(database_url, autocommit=True) as c:
        last_job = c.execute("select coalesce(max(id), 0) from public.jobs").fetchone()
        assert last_job
        course = c.execute(
            "insert into public.courses (owner_id, title) values (%s, 'Bio') returning id",
            (owner,),
        ).fetchone()
        assert course
        material = c.execute(
            "insert into public.materials (course_id, kind, title, storage_path, status)"
            " values (%s, 'textbook', 'Biology', 'x/y/bio.pdf', 'ready') returning id",
            (course[0],),
        ).fetchone()
        assert material

        def section(ordinal: int, title: str, parent: Any = None) -> Any:
            row = c.execute(
                "insert into public.sections (material_id, parent_id, ordinal, level, title)"
                " values (%s, %s, %s, %s, %s) returning id",
                (material[0], parent, ordinal, 1 if parent is None else 2, title),
            ).fetchone()
            assert row
            return row[0]

        root = section(0, "Chapter 1 Cells")
        texts = {
            section(1, "1.1 Structure", root): "The nucleus stores DNA.",
            section(2, "1.2 Function", root): "Ribosomes make proteins.",
            section(3, "Review Questions", root): "Which organelle stores DNA?",
        }
        for ordinal, (section_id, text) in enumerate(texts.items()):
            c.execute(
                "insert into public.chunks (material_id, section_id, ordinal, kind, content,"
                " locations) values (%s, %s, %s, 'text', %s, %s)",
                (material[0], section_id, ordinal, text, json.dumps(HERE)),
            )
    yield {"id": str(root), "owner": owner, "material": str(material[0]), "course": str(course[0])}
    with psycopg.connect(database_url, autocommit=True) as c:
        c.execute("delete from public.jobs where id > %s and kind = 'generate_cards'", last_job)


def rows(database_url: str, sql: str, *params: Any) -> list[tuple[Any, ...]]:
    with psycopg.connect(database_url) as c:
        return c.execute(sql, params).fetchall()


def mark(database_url: str, chapter: dict[str, str]) -> None:
    with psycopg.connect(database_url, autocommit=True) as c:
        c.execute(
            "insert into public.covered_sections (section_id, covered_by) values (%s, %s)",
            (chapter["id"], chapter["owner"]),
        )


def unmark(database_url: str, chapter: dict[str, str]) -> None:
    with psycopg.connect(database_url, autocommit=True) as c:
        c.execute("delete from public.covered_sections where section_id = %s", (chapter["id"],))


async def run(
    database_url: str, chapter: dict[str, str], provider: FakeProvider, attempts: int = 1
) -> None:
    router = Router(Settings(model_card_generation="fake:writer-1"), {"fake": provider})
    handler = cards_job.make_handler(Settings(database_url=database_url), router=router)
    await handler(Job(1, cards_job.KIND, {"section_id": chapter["id"]}, attempts, 3))


def status(database_url: str, chapter: dict[str, str]) -> list[tuple[Any, ...]]:
    return rows(
        database_url,
        "select cards_status::text from public.covered_sections where section_id = %s",
        chapter["id"],
    )


def stored(database_url: str, chapter: dict[str, str]) -> list[tuple[Any, ...]]:
    return rows(
        database_url,
        "select answer, generated_by, prompt_version from public.cards"
        " where section_id = %s order by ordinal",
        chapter["id"],
    )


async def test_marking_a_chapter_queues_its_cards(
    database_url: str, chapter: dict[str, str]
) -> None:
    mark(database_url, chapter)
    assert rows(
        database_url,
        "select status::text from public.jobs where kind = 'generate_cards'"
        " and payload->>'section_id' = %s",
        chapter["id"],
    ) == [("queued",)]
    assert status(database_url, chapter) == [("pending",)]


async def test_cards_are_made_from_the_chapter_but_not_its_review_questions(
    database_url: str, chapter: dict[str, str]
) -> None:
    mark(database_url, chapter)
    provider = FakeProvider()
    await run(database_url, chapter, provider)
    [prompt] = provider.prompts
    assert "Review" not in prompt and "Which organelle" not in prompt
    assert stored(database_url, chapter) == [
        ("The nucleus stores DNA.", "fake:writer-1", "cards-v2"),
        ("Ribosomes make proteins.", "fake:writer-1", "cards-v2"),
    ]
    assert status(database_url, chapter) == [("ready",)]
    assert rows(
        database_url,
        "select job, model, requests, input_tokens, output_tokens from public.llm_usage"
        " where section_id = %s",
        chapter["id"],
    ) == [("generate_cards", "writer-1", 1, 100, 10)]


async def test_marking_again_keeps_the_cards_and_makes_no_more(
    database_url: str, chapter: dict[str, str]
) -> None:
    mark(database_url, chapter)
    await run(database_url, chapter, FakeProvider())
    unmark(database_url, chapter)
    assert len(stored(database_url, chapter)) == 2  # unmarking keeps them

    mark(database_url, chapter)
    provider = FakeProvider()
    await run(database_url, chapter, provider)
    assert provider.prompts == []
    assert len(stored(database_url, chapter)) == 2
    assert status(database_url, chapter) == [("ready",)]


async def test_unmarking_during_generation_stores_nothing(
    database_url: str, chapter: dict[str, str]
) -> None:
    mark(database_url, chapter)
    await run(database_url, chapter, FakeProvider(during=lambda: unmark(database_url, chapter)))
    assert stored(database_url, chapter) == []

    # And a job for a chapter that is no longer covered does nothing at all.
    provider = FakeProvider()
    await run(database_url, chapter, provider)
    assert provider.prompts == []


async def test_status_is_failed_only_after_the_last_attempt(
    database_url: str, chapter: dict[str, str]
) -> None:
    mark(database_url, chapter)
    with pytest.raises(ProviderError):
        await run(database_url, chapter, FakeProvider(fail=ProviderError("declined")), attempts=1)
    assert status(database_url, chapter) == [("pending",)]
    with pytest.raises(ProviderError):
        await run(database_url, chapter, FakeProvider(fail=ProviderError("declined")), attempts=3)
    assert status(database_url, chapter) == [("failed",)]


async def test_a_permanent_error_fails_at_once(database_url: str, chapter: dict[str, str]) -> None:
    mark(database_url, chapter)
    with pytest.raises(ProviderUnavailable):
        await run(database_url, chapter, FakeProvider(fail=ProviderUnavailable("no key")))
    assert status(database_url, chapter) == [("failed",)]


# The API ------------------------------------------------------------------------------


@pytest.fixture
def client() -> Iterator[TestClient]:
    app = create_app()
    app.dependency_overrides[get_verifier] = FakeVerifier
    with TestClient(app) as c:
        yield c


async def test_chapters_show_their_cards(
    client: TestClient,
    database_url: str,
    chapter: dict[str, str],
    make_user: Callable[..., str],
) -> None:
    headers = auth(token_for(chapter["owner"]))
    assert client.put(f"/sections/{chapter['id']}/covered", headers=headers).status_code == 200

    def listed() -> dict[str, Any]:
        body = client.get(f"/courses/{chapter['course']}", headers=headers).json()
        [row] = body["textbooks"][0]["chapters"]
        return {k: row[k] for k in ("cards", "cards_status", "cards_drafted")}

    assert listed() == {"cards": 0, "cards_status": "pending", "cards_drafted": 0}
    # As if an earlier run was cut off partway: a new run counts from zero.
    with psycopg.connect(database_url, autocommit=True) as c:
        c.execute(
            "update public.covered_sections set cards_drafted = 5 where section_id = %s",
            (chapter["id"],),
        )
    await run(database_url, chapter, FakeProvider())
    assert listed() == {"cards": 2, "cards_status": "ready", "cards_drafted": 2}

    cards = client.get(f"/sections/{chapter['id']}/cards", headers=headers).json()
    assert [(c["kind"], c["answer"]) for c in cards] == [
        ("basic", "The nucleus stores DNA."),
        ("basic", "Ribosomes make proteins."),
    ]
    assert cards[0]["sources"] == [
        {"quote": "The nucleus stores DNA.", "heading_path": [], "page": 3}
    ]

    assert client.delete(f"/sections/{chapter['id']}/covered", headers=headers).status_code == 204
    assert listed() == {"cards": 2, "cards_status": None, "cards_drafted": 0}

    other = auth(token_for(make_user()))
    assert client.get(f"/sections/{chapter['id']}/cards", headers=other).status_code == 404
    assert client.get(f"/sections/{uuid.uuid4()}/cards", headers=headers).status_code == 404
