import uuid
from collections.abc import Callable
from typing import Any

import psycopg
from fastapi.testclient import TestClient

from tests.test_api import auth, token_for
from tests.test_review import client, deck  # noqa: F401  (fixtures)


def events(database_url: str, user: str) -> list[tuple[str, uuid.UUID | None, dict[str, Any]]]:
    with psycopg.connect(database_url) as c:
        rows = c.execute(
            "select name, session_id, data from public.usage_events where user_id = %s order by id",
            (user,),
        ).fetchall()
    return [(name, session, data) for name, session, data in rows]


def consent(api: TestClient, admin: str, person: str, consented: bool) -> None:
    response = api.put(
        f"/admin/people/{person}/usage-consent",
        json={"consented": consented},
        headers=auth(token_for(admin)),
    )
    assert response.status_code == 204


def test_nothing_is_logged_until_an_admin_records_consent(
    client: TestClient,  # noqa: F811
    deck: dict[str, Any],  # noqa: F811
    database_url: str,
    make_user: Callable[..., str],
) -> None:
    student = deck["owner"]
    headers = auth(token_for(student))
    card = deck["cards"]["Chapter 2 Genes Q0"]

    client.post(f"/cards/{card}/review", json={"rating": 3}, headers=headers)
    page = {"name": "page_view", "page": "/review"}
    assert client.post("/events", json=page, headers=headers).json() == {"logged": False}
    assert events(database_url, student) == []

    admin = make_user("admin")
    consent(client, admin, student, True)
    [person] = [
        p
        for p in client.get("/admin/people", headers=auth(token_for(admin))).json()
        if p["id"] == student
    ]
    assert person["usage_consent_at"] is not None

    visit = str(uuid.uuid4())
    headers = {**headers, "X-Session": visit}
    client.post(f"/cards/{card}/review", json={"rating": 3, "ms": 4200}, headers=headers)
    assert client.post("/events", json=page, headers=headers).json() == {"logged": True}

    [(review_name, session, review), (page_name, _, viewed)] = events(database_url, student)
    assert (review_name, str(session), page_name) == ("review", visit, "page_view")
    assert viewed == {"page": "/review"}
    assert review["card_id"] == card
    assert (review["rating"], review["ms"], review["kind"]) == (3, 4200, "basic")
    # Rated once before consent: a learning card, seen moments ago.
    assert review["state_before"] == "learning" and review["elapsed_days"] < 0.01
    assert review["scheduled_days"] > 0

    consent(client, admin, student, False)
    client.post("/events", json=page, headers=headers)
    assert len(events(database_url, student)) == 2


def test_changes_are_logged_without_any_text_the_student_wrote(
    client: TestClient,  # noqa: F811
    deck: dict[str, Any],  # noqa: F811
    database_url: str,
    make_user: Callable[..., str],
) -> None:
    student = deck["owner"]
    headers = auth(token_for(student))
    consent(client, make_user("admin"), student, True)
    card = deck["cards"]["Chapter 1 Cells Q0"]

    client.put(f"/cards/{card}/flag", json={"reason": "confusing"}, headers=headers)
    client.delete(f"/cards/{card}/flag", headers=headers)
    client.delete(f"/cards/{card}/flag", headers=headers)  # already back: not logged again
    with psycopg.connect(database_url) as c:
        course = c.execute(
            "select id from public.courses where owner_id = %s", (student,)
        ).fetchone()
    assert course
    secret = "Retake after my appointment"
    date = client.post(
        f"/courses/{course[0]}/dates",
        json={"kind": "exam", "title": secret, "on": "2026-11-13"},
        headers=headers,
    ).json()
    client.delete(f"/dates/{date['id']}", headers=headers)
    client.post(
        "/events",
        json={
            "name": "chat_question",
            "course_id": str(course[0]),
            "first_text_ms": 1500,
            "total_ms": 6000,
            "grounded": True,
            "outside": False,
            "sources": 2,
            "follow_up": False,
            "failed": False,
        },
        headers=headers,
    )

    logged = events(database_url, student)
    assert [name for name, _, _ in logged] == [
        "flag",
        "unflag",
        "date_added",
        "date_deleted",
        "chat_question",
    ]
    assert logged[0][2] == {"card_id": card, "reason": "confusing"}
    assert logged[2][2] == {
        "date_id": date["id"],
        "kind": "exam",
        "on": "2026-11-13",
        "chapters": 0,
    }
    assert secret not in str(logged)


def test_browser_events_are_checked(
    client: TestClient,  # noqa: F811
    deck: dict[str, Any],  # noqa: F811
    make_user: Callable[..., str],
) -> None:
    student = deck["owner"]
    consent(client, make_user("admin"), student, True)
    headers = auth(token_for(student))
    for bad in [
        {"name": "page_view", "page": "/courses/what I typed?"},
        {"name": "search", "query": "anything"},
        {"name": "source_opened", "origin": "email", "page_image": True},
    ]:
        assert client.post("/events", json=bad, headers=headers).status_code == 422


def test_only_admins_record_consent(
    client: TestClient,  # noqa: F811
    deck: dict[str, Any],  # noqa: F811
) -> None:
    student = deck["owner"]
    response = client.put(
        f"/admin/people/{student}/usage-consent",
        json={"consented": True},
        headers=auth(token_for(student)),
    )
    assert response.status_code == 403
