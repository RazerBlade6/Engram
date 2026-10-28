import uuid
from collections.abc import Callable, Iterator
from typing import Any

import psycopg
import pytest
from fastapi.testclient import TestClient

from engram.api.auth import get_verifier
from engram.api.main import create_app
from engram.api.routes.courses import _SectionRow, chapters
from tests.test_api import FakeVerifier, auth, token_for


def section(level: int, title: str) -> _SectionRow:
    return _SectionRow(
        id=uuid.uuid4(),
        material_id=uuid.uuid4(),
        level=level,
        title=title,
        page_start=1,
        page_end=1,
        covered_at=None,
        cards=0,
        cards_status=None,
    )


def titles(sections: list[_SectionRow]) -> list[str]:
    return [s.title for s in chapters(sections)]


def test_chapters_are_the_numbered_chapter_sections() -> None:
    toc = [
        section(1, "Contents"),
        section(1, "Preface"),
        section(1, "Chapter 1 Introduction to Psychology"),
        section(2, "Chapter Outline"),
        section(2, "1.1 What Is Psychology?"),
        section(1, "Chapter 2 Psychological Research"),
        section(1, "References"),
    ]
    assert titles(toc) == [
        "Chapter 1 Introduction to Psychology",
        "Chapter 2 Psychological Research",
    ]


def test_chapters_grouped_into_units_are_still_found() -> None:
    toc = [section(1, "Unit 1 The Chemistry of Life"), section(2, "Chapter IV Cell Structure")]
    assert titles(toc) == ["Chapter IV Cell Structure"]


def test_without_numbered_chapters_the_top_level_minus_matter_is_used() -> None:
    toc = [
        section(1, "Table of Contents"),
        section(1, "1 Cells"),
        section(2, "1.1 Membranes"),
        section(1, "2 Genetics"),
        section(1, "Appendix A Units"),
        section(1, "Index"),
    ]
    assert titles(toc) == ["1 Cells", "2 Genetics"]


@pytest.fixture
def client() -> Iterator[TestClient]:
    app = create_app()
    app.dependency_overrides[get_verifier] = FakeVerifier
    with TestClient(app) as c:
        yield c


@pytest.fixture
def course(database_url: str, make_user: Callable[..., str]) -> dict[str, Any]:
    """A course with a parsed textbook, slides, and a textbook still processing."""
    owner = make_user()
    with psycopg.connect(database_url, autocommit=True) as c:
        course_id = c.execute(
            "insert into public.courses (owner_id, title) values (%s, 'Psychology') returning id",
            (owner,),
        ).fetchone()[0]  # type: ignore[index]

        def material(kind: str, title: str, status: str) -> str:
            material_id = str(uuid.uuid4())
            c.execute(
                "insert into public.materials (id, course_id, kind, title, storage_path, status)"
                " values (%s, %s, %s, %s, %s, %s)",
                (material_id, course_id, kind, title, f"{course_id}/{material_id}/f.pdf", status),
            )
            return material_id

        book = material("textbook", "Psychology 2e", "ready")
        material("slides", "Week 1", "ready")
        material("textbook", "Reader", "processing")
        sections = {}
        for ordinal, (level, title) in enumerate(
            [(1, "Preface"), (1, "Chapter 1 Intro"), (2, "1.1 History"), (1, "Chapter 2 Research")]
        ):
            sections[title] = str(
                c.execute(
                    "insert into public.sections (material_id, ordinal, level, title, page_start,"
                    " page_end) values (%s, %s, %s, %s, %s, %s) returning id",
                    (book, ordinal, level, title, ordinal + 1, ordinal + 1),
                ).fetchone()[0]  # type: ignore[index]
            )
    return {"id": str(course_id), "owner": owner, "book": book, "sections": sections}


def test_course_shows_textbook_chapters_and_all_materials(
    client: TestClient, course: dict[str, Any]
) -> None:
    headers = auth(token_for(course["owner"]))
    body = client.get(f"/courses/{course['id']}", headers=headers).json()
    [textbook] = body["textbooks"]
    assert textbook["title"] == "Psychology 2e"
    assert [c["title"] for c in textbook["chapters"]] == ["Chapter 1 Intro", "Chapter 2 Research"]
    assert all(c["covered_at"] is None for c in textbook["chapters"])
    assert [(m["title"], m["status"]) for m in body["materials"]] == [
        ("Psychology 2e", "ready"),
        ("Week 1", "ready"),
        ("Reader", "processing"),
    ]


def test_marking_and_unmarking_a_chapter(client: TestClient, course: dict[str, Any]) -> None:
    headers = auth(token_for(course["owner"]))
    chapter = course["sections"]["Chapter 1 Intro"]

    first = client.put(f"/sections/{chapter}/covered", headers=headers)
    assert first.status_code == 200
    again = client.put(f"/sections/{chapter}/covered", headers=headers)
    assert again.json()["covered_at"] == first.json()["covered_at"]  # idempotent

    [summary] = [
        c for c in client.get("/courses", headers=headers).json() if c["id"] == course["id"]
    ]
    assert (summary["chapters"], summary["covered"]) == (2, 1)
    body = client.get(f"/courses/{course['id']}", headers=headers).json()
    assert body["textbooks"][0]["chapters"][0]["covered_at"] == first.json()["covered_at"]

    assert client.delete(f"/sections/{chapter}/covered", headers=headers).status_code == 204
    [summary] = [
        c for c in client.get("/courses", headers=headers).json() if c["id"] == course["id"]
    ]
    assert summary["covered"] == 0


def test_other_students_cannot_see_or_mark(
    client: TestClient, course: dict[str, Any], make_user: Callable[..., str]
) -> None:
    headers = auth(token_for(make_user()))
    chapter = course["sections"]["Chapter 1 Intro"]
    assert client.get(f"/courses/{course['id']}", headers=headers).status_code == 404
    assert course["id"] not in [c["id"] for c in client.get("/courses", headers=headers).json()]
    assert client.put(f"/sections/{chapter}/covered", headers=headers).status_code == 404
    assert client.put(f"/sections/{uuid.uuid4()}/covered", headers=headers).status_code == 404


def test_students_create_their_own_courses(
    client: TestClient, make_user: Callable[..., str], database_url: str
) -> None:
    student = make_user()
    response = client.post(
        "/courses", headers=auth(token_for(student)), json={"title": "  Biology 101 "}
    )
    assert response.status_code == 201
    body = response.json()
    assert (body["title"], body["chapters"], body["covered"]) == ("Biology 101", 0, 0)
    with psycopg.connect(database_url) as c:
        row = c.execute("select owner_id::text from public.courses where id = %s", (body["id"],))
        assert row.fetchone() == (student,)
    listed = client.get("/courses", headers=auth(token_for(student))).json()
    assert [c["id"] for c in listed] == [body["id"]]


def test_only_admins_create_courses_for_someone_else(
    client: TestClient, make_user: Callable[..., str], database_url: str
) -> None:
    student, other, admin = make_user(), make_user(), make_user("admin")
    request = {"title": "Politics", "owner_id": other}
    assert (
        client.post("/courses", headers=auth(token_for(student)), json=request).status_code == 403
    )

    response = client.post("/courses", headers=auth(token_for(admin)), json=request)
    assert response.status_code == 201
    with psycopg.connect(database_url) as c:
        row = c.execute(
            "select owner_id::text from public.courses where id = %s", (response.json()["id"],)
        )
        assert row.fetchone() == (other,)

    missing = {"title": "Politics", "owner_id": str(uuid.uuid4())}
    assert client.post("/courses", headers=auth(token_for(admin)), json=missing).status_code == 404


def test_a_course_needs_a_name(client: TestClient, make_user: Callable[..., str]) -> None:
    headers = auth(token_for(make_user()))
    assert client.post("/courses", headers=headers, json={"title": "   "}).status_code == 422
    assert client.post("/courses", headers=headers, json={"title": ""}).status_code == 422
