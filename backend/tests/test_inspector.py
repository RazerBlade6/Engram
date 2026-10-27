import uuid
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any

import psycopg
import pytest
from fastapi.testclient import TestClient
from psycopg import AsyncConnection

from engram.api.auth import get_verifier
from engram.api.main import create_app
from engram.api.pages import PdfPages
from engram.api.routes.inspector import get_pages
from engram.ingest.describe import FigureDescription
from engram.ingest.model import Chunk, Figure, Location, ParsedMaterial, Section
from engram.ingest.store import replace_material_content
from tests.fixtures import textbook
from tests.test_api import FakeVerifier, auth, token_for


class FileStorage:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.downloads = 0

    async def download(self, path: str) -> bytes:
        self.downloads += 1
        return self.path.read_bytes()


@pytest.fixture
def storage(tmp_path: Path) -> FileStorage:
    return FileStorage(textbook.build(tmp_path / "biology.pdf"))


@pytest.fixture
def client(storage: FileStorage) -> Iterator[TestClient]:
    app = create_app()
    app.dependency_overrides[get_verifier] = FakeVerifier
    pages = PdfPages(storage)
    app.dependency_overrides[get_pages] = lambda: pages
    with TestClient(app) as c:
        yield c


@pytest.fixture
async def material(database_url: str, make_user: Callable[..., str]) -> dict[str, str]:
    owner = make_user()
    material_id = str(uuid.uuid4())
    with psycopg.connect(database_url, autocommit=True) as c:
        course = c.execute(
            "insert into public.courses (owner_id, title) values (%s, 'Bio') returning id", (owner,)
        ).fetchone()
        assert course
        c.execute(
            "insert into public.materials"
            " (id, course_id, kind, title, storage_path, status, page_count)"
            " values (%s, %s, 'textbook', 'Biology', %s, 'ready', 2)",
            (material_id, course[0], f"{course[0]}/{material_id}/biology.pdf"),
        )

    first = Location(1, (72.0, 90.0, 300.0, 200.0))
    second_column = Location(1, (320.0, 90.0, 540.0, 150.0))
    parsed = ParsedMaterial(
        page_count=2,
        sections=[Section(0, 1, "Chapter 1 Cells", 1, 2)],
        figures=[Figure(0, Location(1, (100, 400, 300, 600)), b"png", "Figure 1.1", 0, [])],
        chunks=[
            Chunk(0, "text", "Cells are small.", ["Chapter 1 Cells"], [first, second_column], 0),
            Chunk(1, "table", "| a | b |", ["Chapter 1 Cells"], [Location(2, (1, 2, 3, 4))], 0),
            Chunk(
                2,
                "figure",
                "Figure 1.1",
                ["Chapter 1 Cells"],
                [Location(1, (100, 400, 300, 600))],
                0,
                0,
            ),
        ],
    )
    async with await AsyncConnection.connect(database_url) as conn:
        await replace_material_content(
            conn,
            material_id,
            parsed,
            descriptions=[
                FigureDescription(kind="diagram", description="A cell.", labels=["Nucleus"])
            ],
            described_by="fake:vision-1",
            figure_paths=["figures/0.png"],
            chunks=parsed.chunks,
            embeddings=[[0.001] * 384] * 3,
            embedding_model="fake",
        )
    return {"id": material_id, "owner": owner}


def test_inspector_is_admin_only(
    client: TestClient, material: dict[str, str], make_user: Callable[..., str]
) -> None:
    # Even the course owner: the inspector is a tool for whoever runs ingestion.
    for user in (material["owner"], make_user()):
        headers = auth(token_for(user))
        assert client.get("/admin/materials", headers=headers).status_code == 403
        assert client.get(f"/admin/materials/{material['id']}", headers=headers).status_code == 403


def test_list_and_inspect(
    client: TestClient, material: dict[str, str], make_user: Callable[..., str]
) -> None:
    headers = auth(token_for(make_user("admin")))
    listed = {m["id"]: m for m in client.get("/admin/materials", headers=headers).json()}
    summary = listed[material["id"]]
    assert (summary["sections"], summary["figures"], summary["chunks"]) == (1, 1, 3)
    assert summary["course"] == "Bio"

    body: dict[str, Any] = client.get(f"/admin/materials/{material['id']}", headers=headers).json()
    assert body["preview"] is True
    assert [s["title"] for s in body["sections"]] == ["Chapter 1 Cells"]
    # The text chunk spans two columns of page 1 but counts once per box.
    assert body["pages"] == [
        {"page": 1, "text": 2, "tables": 0, "figures": 1},
        {"page": 2, "text": 0, "tables": 1, "figures": 0},
    ]


def test_page_lists_boxes_in_pdf_points(
    client: TestClient, material: dict[str, str], make_user: Callable[..., str]
) -> None:
    headers = auth(token_for(make_user("admin")))
    page = client.get(f"/admin/materials/{material['id']}/pages/1", headers=headers).json()
    assert (page["width"], page["height"]) == (612, 792)  # US Letter
    assert [(c["ordinal"], c["part"], c["parts"], c["bbox"]) for c in page["chunks"]] == [
        (0, 1, 2, [72, 90, 300, 200]),
        (0, 2, 2, [320, 90, 540, 150]),
    ]
    [figure] = page["figures"]
    assert figure["caption"] == "Figure 1.1"
    assert figure["labels"] == ["Nucleus"]
    assert figure["bbox"] == [100, 400, 300, 600]


def test_page_image_is_rendered_once_per_download(
    client: TestClient,
    material: dict[str, str],
    make_user: Callable[..., str],
    storage: FileStorage,
) -> None:
    headers = auth(token_for(make_user("admin")))
    url = f"/admin/materials/{material['id']}/pages"
    first = client.get(f"{url}/1/image", headers=headers)
    assert first.status_code == 200
    assert first.headers["content-type"] == "image/jpeg"
    assert first.content.startswith(b"\xff\xd8")
    assert client.get(f"{url}/2/image", headers=headers).status_code == 200
    assert storage.downloads == 1
    assert client.get(f"{url}/99/image", headers=headers).status_code == 404
    assert client.get(f"{url}/99", headers=headers).status_code == 404
