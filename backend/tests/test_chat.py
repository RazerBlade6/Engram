import json
from collections.abc import AsyncIterator, Callable, Iterator
from typing import Any

import psycopg
import pytest
from fastapi.testclient import TestClient

from engram.api.auth import get_verifier
from engram.api.main import create_app
from engram.api.routes.chat import get_llm
from engram.chat.answer import MARKER, Cited, Outside, Text, answer, search_text
from engram.chat.retrieve import Passage, search
from engram.config import get_settings
from engram.embeddings import get_embedder
from engram.llm import Router, Usage
from engram.llm.base import AnswerEvent, Cite, Document, TextDelta, Turn
from tests.test_api import FakeVerifier, auth, token_for

PASSAGES = {
    "Cells": "Mitochondria carry out cellular respiration, turning glucose into ATP, the energy"
    " the cell can use.",
    "Memory": "The hippocampus is needed to form new long-term memories of events and facts.",
    "History": "Edward Titchener, a student of Wundt, founded structuralism in America.",
}


class FakeProvider:
    """Answers by citing the documents whose titles contain `cite`, one block each."""

    name = "fake"

    def __init__(self, cite: list[str], fail: Exception | None = None) -> None:
        self.cite = cite
        self.fail = fail
        self.documents: list[Document] = []
        self.history: list[Turn] = []

    async def structured(self, *args: Any, **kwargs: Any) -> Any:
        raise NotImplementedError

    async def cited(
        self,
        model: str,
        *,
        system: str,
        documents: list[Document],
        history: list[Turn],
        question: str,
        max_tokens: int = 2048,
        usage: Usage | None = None,
    ) -> AsyncIterator[AnswerEvent]:
        self.documents, self.history = documents, history
        if usage is not None:
            usage.add(Usage(1, 500, 50, models={model}))
        yield TextDelta(0, "Here is what your course says. ")
        if self.fail:
            raise self.fail
        for i, doc in enumerate(documents):
            if any(c in doc.title for c in self.cite):
                yield TextDelta(i + 1, f"About {doc.title}.")
                yield Cite(i + 1, i, doc.text[:20])


# Pieces ------------------------------------------------------------------------------


def test_a_follow_up_is_searched_with_the_question_before_it() -> None:
    history = [Turn("user", "What do mitochondria do?"), Turn("assistant", "They make ATP.")]
    assert search_text("Why?", history) == "What do mitochondria do? Why?"
    assert search_text("What is ATP?", []) == "What is ATP?"


def passage(n: int) -> Passage:
    return Passage(
        chunk_id=f"00000000-0000-0000-0000-00000000000{n}",  # type: ignore[arg-type]
        material_id="00000000-0000-0000-0000-000000000000",  # type: ignore[arg-type]
        book="Bio",
        heading_path=[f"Section {n}"],
        text=f"Passage {n} text",
        page=n,
    )


async def test_sources_are_numbered_in_the_order_they_are_first_cited() -> None:
    provider = scripted(
        [
            TextDelta(0, "A"),
            Cite(0, 2, "q"),
            TextDelta(1, "B"),
            Cite(1, 0, "q"),
            Cite(1, 2, "q"),
            Cite(1, 9, "q"),  # no such document: ignored
        ]
    )
    events = [
        e
        async for e in answer(provider, "m", "Q", [], [passage(0), passage(1), passage(2)], Usage())
    ]
    cites = [
        (e.block, e.source.number, e.first, e.source.passage.page)
        for e in events
        if isinstance(e, Cited)
    ]
    assert cites == [(0, 1, True, 2), (1, 2, True, 0), (1, 1, False, 2)]
    assert [e.text for e in events if isinstance(e, Text)] == ["A", "B"]


def scripted(script: list[AnswerEvent]) -> FakeProvider:
    class Provider(FakeProvider):
        async def cited(self, *args: Any, **kwargs: Any) -> AsyncIterator[AnswerEvent]:
            for event in script:
                yield event

    return Provider([])


async def test_an_answer_outside_the_materials_is_marked_and_the_marker_removed() -> None:
    split = len(MARKER) // 2
    provider = scripted(
        [
            TextDelta(0, MARKER[:split]),
            Cite(0, 0, "q"),
            TextDelta(0, MARKER[split:]),
            TextDelta(0, "\n\n"),
            TextDelta(0, "\nWarm the stock first."),
            TextDelta(1, " Then the rice."),
        ]
    )
    events = [e async for e in answer(provider, "m", "Risotto?", [], [passage(0)], Usage())]
    assert isinstance(events[0], Outside)
    assert [e.text for e in events if isinstance(e, Text)] == [
        "Warm the stock first.",
        " Then the rice.",
    ]
    assert sum(isinstance(e, Cited) for e in events) == 1


async def test_an_answer_that_only_looks_like_the_marker_is_passed_on_whole() -> None:
    provider = scripted([TextDelta(0, "["), TextDelta(0, "Wundt] founded it.")])
    events = [e async for e in answer(provider, "m", "Q", [], [], Usage())]
    assert events == [Text(0, "["), Text(0, "Wundt] founded it.")]


# Retrieval ----------------------------------------------------------------------------


@pytest.fixture
def course(database_url: str, make_user: Callable[..., str]) -> Iterator[dict[str, Any]]:
    """A course with one ready material of three passages, embedded for search. It's a
    PowerPoint, so the source viewer needs no page images from storage."""
    owner = make_user()
    embedder = get_embedder(get_settings().embedding_model)
    with psycopg.connect(database_url, autocommit=True) as c:
        row = c.execute(
            "insert into public.courses (owner_id, title) values (%s, 'Biology') returning id",
            (owner,),
        ).fetchone()
        assert row
        course_id = row[0]
        row = c.execute(
            "insert into public.materials (course_id, kind, title, storage_path, status)"
            " values (%s, 'slides', 'Biology 2e', 'x/y/b.pptx', 'ready') returning id",
            (course_id,),
        ).fetchone()
        assert row
        material = row[0]
        chunks = {}
        for i, (heading, text) in enumerate(PASSAGES.items()):
            vector = embedder.passages([text])[0]
            chunk = c.execute(
                "insert into public.chunks (material_id, ordinal, kind, heading_path, content,"
                " locations, embedding, embedding_model) values (%s, %s, 'text', %s, %s, %s,"
                " %s::extensions.vector, 'test') returning id",
                (
                    material,
                    i,
                    [heading],
                    f"{heading}\n\n{text}",
                    json.dumps([{"page": 10 + i, "bbox": [10, 20, 300, 80]}]),
                    str(vector),
                ),
            ).fetchone()
            assert chunk
            chunks[heading] = str(chunk[0])
    yield {"owner": owner, "id": str(course_id), "material": str(material), "chunks": chunks}


async def test_search_finds_passages_by_meaning_and_by_rare_terms(
    course: dict[str, Any], database_url: str
) -> None:
    embedder = get_embedder(get_settings().embedding_model)
    async with await psycopg.AsyncConnection.connect(database_url) as db:
        # No shared words with the passage: found by meaning.
        energy = "How does a cell get usable energy from sugar?"
        found = await search(db, course["id"], energy, embedder.query(energy))
        assert found[0].heading_path == ["Cells"]
        assert found[0].text == PASSAGES["Cells"] and found[0].page == 10
        assert found[0].title == "Biology 2e · Cells · page 10"
        # A name that small embedding models blur: found by keyword.
        name = "Who was Titchener?"
        found = await search(db, course["id"], name, embedder.query(name))
        assert found[0].heading_path == ["History"]


# The API ------------------------------------------------------------------------------


@pytest.fixture
def make_client() -> Iterator[Callable[[FakeProvider], TestClient]]:
    clients: list[TestClient] = []

    def make(provider: FakeProvider) -> TestClient:
        app = create_app()
        app.dependency_overrides[get_verifier] = FakeVerifier
        app.dependency_overrides[get_llm] = lambda: Router(
            get_settings(),
            {"anthropic": provider},  # type: ignore[dict-item]
        )
        client = TestClient(app)
        client.__enter__()
        clients.append(client)
        return client

    yield make
    for client in clients:
        client.__exit__(None, None, None)


def events(response: Any) -> list[tuple[str, dict[str, Any]]]:
    out = []
    for chunk in response.text.strip().split("\n\n"):
        name, data = chunk.split("\n")
        out.append((name.removeprefix("event: "), json.loads(data.removeprefix("data: "))))
    return out


def test_an_answer_streams_with_its_sources(
    make_client: Callable[[FakeProvider], TestClient], course: dict[str, Any], database_url: str
) -> None:
    provider = FakeProvider(cite=["Memory"])
    client = make_client(provider)
    with psycopg.connect(database_url) as c:
        before = c.execute("select count(*) from public.llm_usage where job = 'chat'").fetchone()
    response = client.post(
        f"/courses/{course['id']}/ask",
        json={
            "question": "What does it do?",
            "history": [
                {"role": "user", "text": "Tell me about the hippocampus"},
                {"role": "assistant", "text": "It's in the brain."},
            ],
        },
        headers=auth(token_for(course["owner"])),
    )
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    got = events(response)
    names = [name for name, _ in got]
    assert names[0] == "text" and names[-1] == "done"
    source = next(data for name, data in got if name == "source")
    assert source == {
        "number": 1,
        "chunk_id": course["chunks"]["Memory"],
        "material_id": course["material"],
        "book": "Biology 2e",
        "heading_path": ["Memory"],
        "page": 11,
    }
    cite = next(data for name, data in got if name == "cite")
    assert cite["source"] == 1 and cite["quote"] == PASSAGES["Memory"][:20]
    assert got[-1] == ("done", {"grounded": True})
    # The follow-up was searched with the question before it, and the history passed on.
    assert any("Memory" in d.title for d in provider.documents)
    assert [t.role for t in provider.history] == ["user", "assistant"]
    with psycopg.connect(database_url) as c:
        after = c.execute("select count(*) from public.llm_usage where job = 'chat'").fetchone()
    assert before and after and after[0] == before[0] + 1


def test_an_uncited_answer_is_not_grounded_and_a_failure_is_reported(
    make_client: Callable[[FakeProvider], TestClient], course: dict[str, Any]
) -> None:
    headers = auth(token_for(course["owner"]))
    url = f"/courses/{course['id']}/ask"
    got = events(
        make_client(FakeProvider(cite=[])).post(url, json={"question": "Q?"}, headers=headers)
    )
    assert got[-1] == ("done", {"grounded": False})

    failing = FakeProvider(cite=[], fail=RuntimeError("overloaded"))
    got = events(make_client(failing).post(url, json={"question": "Q?"}, headers=headers))
    assert got[-1][0] == "error"


def test_others_cannot_ask_about_or_open_a_course(
    make_client: Callable[[FakeProvider], TestClient],
    course: dict[str, Any],
    make_user: Callable[..., str],
) -> None:
    client = make_client(FakeProvider(cite=[]))
    other = auth(token_for(make_user()))
    ask = client.post(f"/courses/{course['id']}/ask", json={"question": "Q?"}, headers=other)
    assert ask.status_code == 404
    chunk = course["chunks"]["Memory"]
    assert client.get(f"/chunks/{chunk}/source", headers=other).status_code == 404
    page = client.get(f"/materials/{course['material']}/pages/11/image", headers=other)
    assert page.status_code == 404


def test_a_source_opens_on_its_passage(
    make_client: Callable[[FakeProvider], TestClient], course: dict[str, Any]
) -> None:
    client = make_client(FakeProvider(cite=[]))
    chunk = course["chunks"]["Memory"]
    response = client.get(f"/chunks/{chunk}/source", headers=auth(token_for(course["owner"])))
    assert response.status_code == 200
    body = response.json()
    assert body["passage"] == PASSAGES["Memory"]
    assert body["page"] == 11 and body["boxes"] == [{"page": 11, "bbox": [10, 20, 300, 80]}]
    assert (body["width"], body["height"]) == (None, None)  # not a PDF: no page image
