from collections.abc import Callable, Iterator

import psycopg
import pytest
from fastapi.testclient import TestClient

from engram.api.auth import get_verifier
from engram.api.main import create_app
from tests.test_api import FakeVerifier, auth, token_for


@pytest.fixture
def client() -> Iterator[TestClient]:
    app = create_app()
    app.dependency_overrides[get_verifier] = FakeVerifier
    with TestClient(app) as c:
        yield c


@pytest.fixture
def owner(database_url: str, make_user: Callable[..., str]) -> tuple[str, dict[str, str]]:
    """A student with two courses; returns their id and each course's id by title."""
    user = make_user()
    with psycopg.connect(database_url, autocommit=True) as c:
        courses = {
            title: str(
                c.execute(
                    "insert into public.courses (owner_id, title) values (%s, %s) returning id",
                    (user, title),
                ).fetchone()[0]  # type: ignore[index]
            )
            for title in ("Psychology", "Biology")
        }
    return user, courses


def test_dates_are_added_listed_in_order_changed_and_deleted(
    client: TestClient, owner: tuple[str, dict[str, str]]
) -> None:
    user, courses = owner
    headers = auth(token_for(user))

    def add(course: str, kind: str, title: str, on: str) -> dict[str, str]:
        response = client.post(
            f"/courses/{courses[course]}/dates",
            json={"kind": kind, "title": title, "on": on},
            headers=headers,
        )
        assert response.status_code == 201
        body: dict[str, str] = response.json()
        return body

    midterm = add("Psychology", "exam", "  Midterm ", "2026-11-13")
    assert midterm["title"] == "Midterm"
    assert midterm["course"] == "Psychology"
    add("Biology", "quiz", "Quiz 2", "2026-11-04")
    add("Biology", "deadline", "Lab report", "2026-11-13")

    listed = client.get("/dates", headers=headers).json()
    assert [(d["on"], d["course"], d["title"]) for d in listed] == [
        ("2026-11-04", "Biology", "Quiz 2"),
        ("2026-11-13", "Biology", "Lab report"),
        ("2026-11-13", "Psychology", "Midterm"),
    ]

    changed = client.put(
        f"/dates/{midterm['id']}",
        json={"kind": "exam", "title": "Midterm 1", "on": "2026-11-14"},
        headers=headers,
    ).json()
    assert (changed["title"], changed["on"]) == ("Midterm 1", "2026-11-14")

    assert client.delete(f"/dates/{midterm['id']}", headers=headers).status_code == 204
    assert len(client.get("/dates", headers=headers).json()) == 2


def test_others_cannot_see_or_touch_a_students_dates(
    client: TestClient, owner: tuple[str, dict[str, str]], make_user: Callable[..., str]
) -> None:
    user, courses = owner
    course = courses["Psychology"]
    new = {"kind": "exam", "title": "Final", "on": "2026-12-10"}
    final = client.post(f"/courses/{course}/dates", json=new, headers=auth(token_for(user))).json()

    other = auth(token_for(make_user()))
    assert client.get("/dates", headers=other).json() == []
    assert client.post(f"/courses/{course}/dates", json=new, headers=other).status_code == 404
    assert client.put(f"/dates/{final['id']}", json=new, headers=other).status_code == 404
    client.delete(f"/dates/{final['id']}", headers=other)
    assert len(client.get("/dates", headers=auth(token_for(user))).json()) == 1


@pytest.mark.parametrize(
    "body",
    [
        {"kind": "exam", "title": "   ", "on": "2026-11-13"},
        {"kind": "lecture", "title": "Week 3", "on": "2026-11-13"},
        {"kind": "exam", "title": "Midterm", "on": "0202-11-13"},
    ],
)
def test_blank_titles_unknown_kinds_and_mistyped_years_are_refused(
    client: TestClient, owner: tuple[str, dict[str, str]], body: dict[str, str]
) -> None:
    user, courses = owner
    response = client.post(
        f"/courses/{courses['Psychology']}/dates", json=body, headers=auth(token_for(user))
    )
    assert response.status_code == 422
