import json
from collections.abc import Callable, Iterator
from datetime import UTC, datetime, timedelta
from typing import Any

import psycopg
import pytest
from fastapi.testclient import TestClient

from engram import review as scheduling
from engram.api.auth import get_verifier
from engram.api.main import create_app
from engram.api.routes.review import highlight
from engram.review import Day, preview, review
from tests.test_api import FakeVerifier, auth, token_for

NOW = datetime(2026, 10, 27, 12, tzinfo=UTC)


# Scheduling ---------------------------------------------------------------------------


def test_a_new_card_learns_in_minutes_then_moves_to_days() -> None:
    first = review(None, 3, NOW)
    assert (first.state, first.due - NOW) == ("learning", timedelta(minutes=10))
    second = review(first, 3, first.due)
    assert second.state == "review" and second.due - first.due >= timedelta(days=1)
    lapse = review(second, 1, second.due)
    assert lapse.state == "relearning" and lapse.due - second.due < timedelta(hours=1)


def test_preview_orders_the_ratings() -> None:
    times = preview(None, NOW)
    assert NOW < times[1] < times[2] < times[3] < times[4]


def test_the_day_follows_the_students_time_zone() -> None:
    # 23:30 on the 26th in Los Angeles is already the 27th in UTC.
    late = datetime(2026, 10, 27, 6, 30, tzinfo=UTC)
    day = Day.of(late, scheduling.timezone("America/Los_Angeles"))
    assert day.start == datetime(2026, 10, 26, 7, tzinfo=UTC)
    assert day.end == datetime(2026, 10, 27, 7, tzinfo=UTC)
    assert scheduling.timezone("Not/AZone").key == "UTC"


def test_highlight_finds_the_quote_despite_spacing() -> None:
    passage = "Cells are small.\nThe nucleus   stores DNA, mostly."
    span = highlight(passage, "the nucleus stores DNA")
    assert span and passage[slice(*span)] == "The nucleus   stores DNA"
    assert highlight(passage, "ribosomes make proteins") is None


# The API ------------------------------------------------------------------------------


@pytest.fixture
def client() -> Iterator[TestClient]:
    app = create_app()
    app.dependency_overrides[get_verifier] = FakeVerifier
    with TestClient(app) as c:
        yield c


@pytest.fixture
def deck(database_url: str, make_user: Callable[..., str]) -> dict[str, Any]:
    """A course whose two chapters have cards; chapter 2 was covered first."""
    owner = make_user()
    with psycopg.connect(database_url, autocommit=True) as c:
        last_job = c.execute("select coalesce(max(id), 0) from public.jobs").fetchone()
        course = c.execute(
            "insert into public.courses (owner_id, title) values (%s, 'Biology') returning id",
            (owner,),
        ).fetchone()
        assert course and last_job
        material = c.execute(
            "insert into public.materials (course_id, kind, title, storage_path, status)"
            " values (%s, 'textbook', 'Biology 2e', 'x/y/b.pdf', 'ready') returning id",
            (course[0],),
        ).fetchone()
        assert material
        cards: dict[str, str] = {}
        for ordinal, chapter in enumerate(["Chapter 1 Cells", "Chapter 2 Genes"]):
            section = c.execute(
                "insert into public.sections (material_id, ordinal, level, title)"
                " values (%s, %s, 1, %s) returning id",
                (material[0], ordinal, chapter),
            ).fetchone()
            assert section
            chunk = c.execute(
                "insert into public.chunks (material_id, section_id, ordinal, kind, heading_path,"
                " content, locations) values (%s, %s, %s, 'text', %s, %s, %s) returning id",
                (
                    material[0],
                    section[0],
                    ordinal,
                    [chapter],
                    f"{chapter}\n\nIntro. The fact about {chapter} is here.",
                    json.dumps([{"page": ordinal + 5, "bbox": [0, 0, 1, 1]}]),
                ),
            ).fetchone()
            assert chunk
            for i in range(2):
                source = {
                    "chunk_id": str(chunk[0]),
                    "quote": f"the fact about {chapter}",
                    "heading_path": [chapter],
                    "locations": [{"page": ordinal + 5, "bbox": [0, 0, 1, 1]}],
                }
                row = c.execute(
                    "insert into public.cards (material_id, section_id, ordinal, kind, concept,"
                    " prompt, answer, sources, generated_by, prompt_version)"
                    " values (%s, %s, %s, 'basic', 'c', %s, 'A', %s, 'm', 'v') returning id",
                    (material[0], section[0], i, f"{chapter} Q{i}", json.dumps([source])),
                ).fetchone()
                assert row
                cards[f"{chapter} Q{i}"] = str(row[0])
            if ordinal == 1:
                c.execute(
                    "insert into public.covered_sections (section_id, covered_by, covered_at)"
                    " values (%s, %s, now() - interval '1 day')",
                    (section[0], owner),
                )
    yield {"owner": owner, "cards": cards}
    with psycopg.connect(database_url, autocommit=True) as c:
        c.execute("delete from public.jobs where id > %s and kind = 'generate_cards'", last_job)


def prompts(client: TestClient, user: str) -> list[str]:
    body = client.get("/review/queue", headers=auth(token_for(user))).json()
    return [c["prompt"] for c in body["cards"]]


def test_new_cards_are_introduced_a_few_a_day_covered_chapters_first(
    client: TestClient, deck: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(scheduling, "NEW_PER_DAY", 3)
    headers = auth(token_for(deck["owner"]))
    body = client.get("/review/queue", headers=headers).json()
    assert [c["prompt"] for c in body["cards"]] == [
        "Chapter 2 Genes Q0",
        "Chapter 2 Genes Q1",
        "Chapter 1 Cells Q0",
    ]
    first = body["cards"][0]
    assert first["new"] and (first["course"], first["chapter"]) == ("Biology", "Chapter 2 Genes")
    source = first["source"]
    assert source["passage"] == "Intro. The fact about Chapter 2 Genes is here."
    assert source["passage"][slice(*source["highlight"])] == "The fact about Chapter 2 Genes"
    assert (source["book"], source["page"]) == ("Biology 2e", 6)

    summary = client.get("/review/summary", headers=headers).json()
    assert summary == {"due": 0, "new": 3, "minutes": 1, "courses": ["Biology"]}


def test_rating_schedules_the_card(
    client: TestClient, deck: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(scheduling, "NEW_PER_DAY", 1)
    headers = auth(token_for(deck["owner"]))
    card = deck["cards"]["Chapter 2 Genes Q0"]

    first = client.post(f"/cards/{card}/review", json={"rating": 3}, headers=headers)
    assert first.status_code == 200
    # In its learning steps, it's due again within minutes: still in today's queue, not new.
    # Today's one new card has been used.
    body = client.get("/review/queue", headers=headers).json()
    assert [(c["prompt"], c["new"]) for c in body["cards"]] == [("Chapter 2 Genes Q0", False)]

    client.post(f"/cards/{card}/review", json={"rating": 3}, headers=headers)
    assert prompts(client, deck["owner"]) == []  # next due in days

    bad = client.post(f"/cards/{card}/review", json={"rating": 5}, headers=headers)
    assert bad.status_code == 422


def test_flagging_takes_a_card_out_until_unflagged(
    client: TestClient, deck: dict[str, Any], database_url: str
) -> None:
    headers = auth(token_for(deck["owner"]))
    card = deck["cards"]["Chapter 2 Genes Q0"]
    flagged = client.put(f"/cards/{card}/flag", json={"reason": "confusing"}, headers=headers)
    assert flagged.status_code == 204
    assert "Chapter 2 Genes Q0" not in prompts(client, deck["owner"])
    with psycopg.connect(database_url) as c:
        assert c.execute(
            "select flag::text from public.card_progress where card_id = %s", (card,)
        ).fetchall() == [("confusing",)]

    assert client.delete(f"/cards/{card}/flag", headers=headers).status_code == 204
    assert "Chapter 2 Genes Q0" in prompts(client, deck["owner"])


def test_other_students_and_admins_cannot_review_someone_elses_cards(
    client: TestClient, deck: dict[str, Any], make_user: Callable[..., str]
) -> None:
    card = deck["cards"]["Chapter 1 Cells Q0"]
    other = auth(token_for(make_user()))
    assert (
        client.post(f"/cards/{card}/review", json={"rating": 3}, headers=other).status_code == 404
    )
    flag = client.put(f"/cards/{card}/flag", json={"reason": "wrong"}, headers=other)
    assert flag.status_code == 404
    # Admins can read every course, but their reviews hold only their own courses' cards.
    assert prompts(client, make_user("admin")) == []
