import time
import uuid
from collections.abc import Callable, Iterator
from typing import Any

import jwt
import psycopg
import pytest
from cryptography.hazmat.primitives.asymmetric import ec
from fastapi.testclient import TestClient

from engram.api.auth import get_verifier
from engram.api.main import create_app
from engram.api.routes.admin import get_accounts

ISSUER = "http://supabase.test/auth/v1"
_key = ec.generate_private_key(ec.SECP256R1())


class FakeVerifier:
    """Verifies tokens signed with a throwaway test key, the way Supabase-issued ones are."""

    issuer = ISSUER

    def verify(self, token: str) -> dict[str, Any]:
        claims: dict[str, Any] = jwt.decode(
            token,
            _key.public_key(),
            algorithms=["ES256"],
            audience="authenticated",
            issuer=ISSUER,
        )
        return claims


def token_for(user_id: str, *, role: str = "authenticated", expires_in: int = 300) -> str:
    now = int(time.time())
    claims = {
        "sub": user_id,
        "role": role,
        "aud": "authenticated",
        "iss": ISSUER,
        "iat": now,
        "exp": now + expires_in,
    }
    return jwt.encode(claims, _key, algorithm="ES256")


@pytest.fixture
def client() -> Iterator[TestClient]:
    app = create_app()
    app.dependency_overrides[get_verifier] = FakeVerifier
    with TestClient(app) as c:
        yield c


def auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


class FakeAccounts:
    """Supabase Auth's admin API, without Auth: CI runs only the database. Deleting removes the
    auth user directly, so the cascades are real; reset emails are only recorded."""

    def __init__(self, database_url: str) -> None:
        self.database_url = database_url
        self.resets: list[uuid.UUID] = []

    async def delete(self, user_id: uuid.UUID) -> bool:
        with psycopg.connect(self.database_url, autocommit=True) as c:
            return c.execute("delete from auth.users where id = %s", (user_id,)).rowcount > 0

    async def send_password_reset(self, user_id: uuid.UUID) -> bool:
        with psycopg.connect(self.database_url) as c:
            found = c.execute("select 1 from auth.users where id = %s", (user_id,)).fetchone()
        if found:
            self.resets.append(user_id)
        return found is not None


def test_health() -> None:
    response = TestClient(create_app()).get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_me_requires_a_valid_token(client: TestClient, database_url: str) -> None:
    assert client.get("/me").status_code == 401
    assert client.get("/me", headers=auth("not-a-jwt")).status_code == 401
    expired = token_for("00000000-0000-0000-0000-000000000000", expires_in=-60)
    assert client.get("/me", headers=auth(expired)).status_code == 401
    anon = token_for("00000000-0000-0000-0000-000000000000", role="anon")
    assert client.get("/me", headers=auth(anon)).status_code == 401


def test_me_returns_own_profile(
    client: TestClient, make_user: Callable[..., str], database_url: str
) -> None:
    user_id = make_user()
    response = client.get("/me", headers=auth(token_for(user_id)))
    assert response.status_code == 200
    assert response.json() == {
        "id": user_id,
        "display_name": None,
        "role": "student",
        "welcomed_at": None,
    }


def test_the_welcome_tour_is_remembered_per_account(
    client: TestClient, make_user: Callable[..., str], database_url: str
) -> None:
    headers = auth(token_for(make_user()))
    assert client.put("/me/welcomed", headers=headers).status_code == 204
    first = client.get("/me", headers=headers).json()["welcomed_at"]
    assert first is not None
    # Seeing it again (another device that hadn't loaded the profile yet) keeps the first time.
    assert client.put("/me/welcomed", headers=headers).status_code == 204
    assert client.get("/me", headers=headers).json()["welcomed_at"] == first


def test_invites_are_admin_only(
    client: TestClient, make_user: Callable[..., str], database_url: str
) -> None:
    student = make_user()
    response = client.post(
        "/admin/invites", headers=auth(token_for(student)), json={"email": "new@example.com"}
    )
    assert response.status_code == 403


def test_admins_send_password_resets(
    client: TestClient, make_user: Callable[..., str], database_url: str
) -> None:
    accounts = FakeAccounts(database_url)
    client.app.dependency_overrides[get_accounts] = lambda: accounts  # type: ignore[attr-defined]
    student = make_user()
    url = f"/admin/people/{student}/password-reset"
    assert client.post(url, headers=auth(token_for(student))).status_code == 403

    admin = auth(token_for(make_user("admin")))
    assert client.post(url, headers=admin).status_code == 204
    assert [str(r) for r in accounts.resets] == [student]
    missing = f"/admin/people/{uuid.uuid4()}/password-reset"
    assert client.post(missing, headers=admin).status_code == 404
