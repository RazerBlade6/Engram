import io
import uuid
import zipfile
from collections.abc import Callable, Iterator
from typing import Any

import psycopg
import pytest
from fastapi.testclient import TestClient

from engram.api.auth import get_verifier
from engram.api.main import create_app
from engram.api.routes import materials
from engram.api.routes.materials import get_storage
from tests.test_api import FakeVerifier, auth, token_for

PDF_BYTES = b"%PDF-1.4\n% a lecture\n%%EOF\n"


def pptx_bytes(*, presentation: bool = True) -> bytes:
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w") as archive:
        archive.writestr("[Content_Types].xml", "<Types/>")
        archive.writestr("ppt/presentation.xml" if presentation else "word/document.xml", "<x/>")
    return out.getvalue()


class FakeStorage:
    def __init__(self) -> None:
        self.objects: dict[str, tuple[bytes, str]] = {}

    async def upload(self, path: str, data: bytes, content_type: str) -> None:
        self.objects[path] = (data, content_type)

    async def remove_prefix(self, prefix: str) -> None:
        for key in [k for k in self.objects if k.rsplit("/", 1)[0] == prefix]:
            del self.objects[key]


@pytest.fixture
def storage() -> FakeStorage:
    return FakeStorage()


@pytest.fixture
def client(storage: FakeStorage) -> Iterator[TestClient]:
    app = create_app()
    app.dependency_overrides[get_verifier] = FakeVerifier
    app.dependency_overrides[get_storage] = lambda: storage
    with TestClient(app) as c:
        yield c


@pytest.fixture
def course(database_url: str, make_user: Callable[..., str]) -> Iterator[dict[str, str]]:
    """A course with a textbook. Uploads queue real ingestion jobs; they are removed afterwards
    so they can't be claimed by tests that run the worker."""
    owner = make_user()
    with psycopg.connect(database_url, autocommit=True) as c:
        last_job = c.execute("select coalesce(max(id), 0) from public.jobs").fetchone()
        assert last_job
        row = c.execute(
            "insert into public.courses (owner_id, title) values (%s, 'Psychology') returning id",
            (owner,),
        ).fetchone()
        assert row
        textbook = c.execute(
            "insert into public.materials (course_id, kind, title, storage_path, status)"
            " values (%s, 'textbook', 'Psychology 2e', %s, 'ready') returning id",
            (row[0], f"{row[0]}/book/psych.pdf"),
        ).fetchone()
        assert textbook
    yield {"id": str(row[0]), "owner": owner, "textbook": str(textbook[0])}
    with psycopg.connect(database_url, autocommit=True) as c:
        c.execute(
            "delete from public.jobs where id > %s and kind = 'ingest_material'", (last_job[0],)
        )


def rows(database_url: str, sql: str, *params: Any) -> list[tuple[Any, ...]]:
    with psycopg.connect(database_url) as c:
        return c.execute(sql, params).fetchall()


def upload(
    client: TestClient, course: dict[str, str], name: str, data: bytes, user: str = ""
) -> Any:
    return client.post(
        f"/courses/{course['id']}/materials",
        headers=auth(token_for(user or course["owner"])),
        files={"file": (name, data, "application/octet-stream")},
    )


def test_upload_stores_and_queues_slides(
    client: TestClient, course: dict[str, str], storage: FakeStorage, database_url: str
) -> None:
    response = upload(client, course, "Week_3 Biopsychology.pdf", PDF_BYTES)
    assert response.status_code == 201
    body = response.json()
    assert (body["title"], body["kind"], body["status"]) == (
        "Week 3 Biopsychology",
        "slides",
        "queued",
    )

    [(path, added_by, status)] = rows(
        database_url,
        "select storage_path, added_by::text, status::text from public.materials where id = %s",
        body["id"],
    )
    assert (added_by, status) == (course["owner"], "queued")
    assert storage.objects[path] == (PDF_BYTES, "application/pdf")
    assert path == f"{course['id']}/{body['id']}/Week_3-Biopsychology.pdf"
    assert rows(
        database_url,
        "select kind from public.jobs where payload->>'material_id' = %s",
        body["id"],
    ) == [("ingest_material",)]


def test_powerpoint_is_recognised_by_content(
    client: TestClient, course: dict[str, str], storage: FakeStorage
) -> None:
    # The name says PDF; the content is a PowerPoint file, and it is stored as one.
    response = upload(client, course, "lecture.pdf", pptx_bytes())
    assert response.status_code == 201
    [(path, (_, content_type))] = storage.objects.items()
    assert path.endswith("/lecture.pptx")
    assert content_type.endswith("presentationml.presentation")


@pytest.mark.parametrize(
    ("name", "data"),
    [
        ("notes.txt", b"just text"),
        ("essay.docx", pptx_bytes(presentation=False)),
        ("old.ppt", b"\xd0\xcf\x11\xe0"),
    ],
)
def test_other_files_are_refused(
    client: TestClient,
    course: dict[str, str],
    storage: FakeStorage,
    database_url: str,
    name: str,
    data: bytes,
) -> None:
    response = upload(client, course, name, data)
    assert response.status_code == 415
    assert "PDF and PowerPoint" in response.json()["detail"]
    assert storage.objects == {}
    assert rows(
        database_url, "select count(*) from public.materials where course_id = %s", course["id"]
    ) == [(1,)]


def test_large_files_are_refused(
    client: TestClient, course: dict[str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(materials, "MAX_UPLOAD_BYTES", 10)
    response = upload(client, course, "big.pdf", PDF_BYTES)
    assert response.status_code == 413


def test_other_students_cannot_upload_or_remove(
    client: TestClient,
    course: dict[str, str],
    storage: FakeStorage,
    make_user: Callable[..., str],
) -> None:
    other = make_user()
    assert upload(client, course, "x.pdf", PDF_BYTES, user=other).status_code == 404
    assert storage.objects == {}

    mine = upload(client, course, "Week 1.pdf", PDF_BYTES).json()
    headers = auth(token_for(other))
    assert client.delete(f"/materials/{mine['id']}", headers=headers).status_code == 404
    assert len(storage.objects) == 1


def test_students_remove_their_slides_but_not_the_textbook(
    client: TestClient, course: dict[str, str], storage: FakeStorage, database_url: str
) -> None:
    headers = auth(token_for(course["owner"]))
    mine = upload(client, course, "Week 1.pdf", PDF_BYTES).json()
    assert client.delete(f"/materials/{mine['id']}", headers=headers).status_code == 204
    assert storage.objects == {}
    assert rows(database_url, "select 1 from public.materials where id = %s", mine["id"]) == []

    response = client.delete(f"/materials/{course['textbook']}", headers=headers)
    assert response.status_code == 404
    assert rows(
        database_url, "select 1 from public.materials where id = %s", course["textbook"]
    ) == [(1,)]


def test_unknown_course(client: TestClient, course: dict[str, str]) -> None:
    missing = {**course, "id": str(uuid.uuid4())}
    assert upload(client, missing, "x.pdf", PDF_BYTES).status_code == 404
