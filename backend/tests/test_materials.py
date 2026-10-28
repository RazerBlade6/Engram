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
    """Storage where `put` stands in for the browser's upload with a token."""

    def __init__(self) -> None:
        self.objects: dict[str, bytes] = {}
        self.tokens: dict[str, str] = {}

    async def upload_token(self, path: str) -> str:
        self.tokens[path] = f"token-{len(self.tokens)}"
        return self.tokens[path]

    def put(self, path: str, token: str, data: bytes) -> None:
        assert self.tokens[path] == token
        self.objects[path] = data

    async def head(self, path: str, length: int) -> tuple[bytes, int] | None:
        data = self.objects.get(path)
        return None if data is None else (data[:length], len(data))

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


def add(
    client: TestClient,
    course: dict[str, str],
    name: str,
    size: int = 100,
    kind: str = "slides",
    user: str = "",
) -> Any:
    return client.post(
        f"/courses/{course['id']}/materials",
        headers=auth(token_for(user or course["owner"])),
        json={"filename": name, "size": size, "kind": kind},
    )


def upload(
    client: TestClient,
    storage: FakeStorage,
    course: dict[str, str],
    name: str,
    data: bytes,
    kind: str = "slides",
    user: str = "",
) -> Any:
    """All three steps: add the material, upload the file, queue it."""
    user = user or course["owner"]
    added = add(client, course, name, len(data), kind, user)
    if added.status_code != 201:
        return added
    body = added.json()
    storage.put(body["upload"]["path"], body["upload"]["token"], data)
    return client.post(f"/materials/{body['material']['id']}/queue", headers=auth(token_for(user)))


def test_upload_stores_and_queues_slides(
    client: TestClient, course: dict[str, str], storage: FakeStorage, database_url: str
) -> None:
    added = add(client, course, "Week_3 Biopsychology.pdf", len(PDF_BYTES))
    assert added.status_code == 201
    body = added.json()
    material = body["material"]
    assert (material["title"], material["kind"], material["status"]) == (
        "Week 3 Biopsychology",
        "slides",
        "uploading",
    )
    path = body["upload"]["path"]
    assert path == f"{course['id']}/{material['id']}/Week_3-Biopsychology.pdf"

    headers = auth(token_for(course["owner"]))
    # Queuing before the file arrives is refused, and the material waits.
    assert client.post(f"/materials/{material['id']}/queue", headers=headers).status_code == 409

    storage.put(path, body["upload"]["token"], PDF_BYTES)
    queued = client.post(f"/materials/{material['id']}/queue", headers=headers)
    assert queued.status_code == 200
    assert queued.json()["status"] == "queued"

    [(added_by, status)] = rows(
        database_url,
        "select added_by::text, status::text from public.materials where id = %s",
        material["id"],
    )
    assert (added_by, status) == (course["owner"], "queued")
    assert rows(
        database_url,
        "select kind from public.jobs where payload->>'material_id' = %s",
        material["id"],
    ) == [("ingest_material",)]
    # Only once.
    assert client.post(f"/materials/{material['id']}/queue", headers=headers).status_code == 404


def test_powerpoint_is_accepted(
    client: TestClient, course: dict[str, str], storage: FakeStorage
) -> None:
    response = upload(client, storage, course, "lecture.pptx", pptx_bytes())
    assert response.status_code == 200
    [path] = storage.objects
    assert path.endswith("/lecture.pptx")


@pytest.mark.parametrize("name", ["notes.txt", "essay.docx", "old.ppt"])
def test_other_file_types_are_refused_before_upload(
    client: TestClient, course: dict[str, str], storage: FakeStorage, name: str
) -> None:
    response = add(client, course, name)
    assert response.status_code == 415
    assert "PDF and PowerPoint" in response.json()["detail"]
    assert storage.tokens == {}


@pytest.mark.parametrize(
    ("name", "data"), [("notes.pdf", b"just text"), ("essay.pptx", b"\xd0\xcf\x11\xe0")]
)
def test_a_file_that_isnt_what_it_says_is_removed(
    client: TestClient,
    course: dict[str, str],
    storage: FakeStorage,
    database_url: str,
    name: str,
    data: bytes,
) -> None:
    response = upload(client, storage, course, name, data)
    assert response.status_code == 415
    assert "PDF and PowerPoint" in response.json()["detail"]
    assert storage.objects == {}
    assert rows(
        database_url, "select count(*) from public.materials where course_id = %s", course["id"]
    ) == [(1,)]


def test_large_files_are_refused(
    client: TestClient, course: dict[str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setitem(materials.MAX_UPLOAD_BYTES, "slides", 10)
    assert add(client, course, "big.pdf", size=11).status_code == 413


def test_only_admins_add_textbooks(
    client: TestClient,
    course: dict[str, str],
    storage: FakeStorage,
    make_user: Callable[..., str],
    database_url: str,
) -> None:
    response = add(client, course, "Biology 2e.pdf", kind="textbook")
    assert response.status_code == 403
    assert storage.tokens == {}

    admin = make_user("admin")
    response = upload(client, storage, course, "Biology 2e.pdf", PDF_BYTES, "textbook", admin)
    assert response.status_code == 200
    assert (response.json()["kind"], response.json()["status"]) == ("textbook", "queued")
    assert rows(
        database_url,
        "select added_by::text from public.materials where id = %s",
        response.json()["id"],
    ) == [(admin,)]


def test_other_students_cannot_upload_or_remove(
    client: TestClient,
    course: dict[str, str],
    storage: FakeStorage,
    make_user: Callable[..., str],
) -> None:
    other = make_user()
    assert add(client, course, "x.pdf", user=other).status_code == 404
    assert storage.tokens == {}

    mine = add(client, course, "Week 1.pdf").json()
    headers = auth(token_for(other))
    storage.put(mine["upload"]["path"], mine["upload"]["token"], PDF_BYTES)
    material = mine["material"]["id"]
    assert client.post(f"/materials/{material}/queue", headers=headers).status_code == 404
    assert client.delete(f"/materials/{material}", headers=headers).status_code == 404
    assert len(storage.objects) == 1


def test_students_remove_their_slides_but_not_the_textbook(
    client: TestClient, course: dict[str, str], storage: FakeStorage, database_url: str
) -> None:
    headers = auth(token_for(course["owner"]))
    mine = upload(client, storage, course, "Week 1.pdf", PDF_BYTES).json()
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
    assert add(client, missing, "x.pdf").status_code == 404
