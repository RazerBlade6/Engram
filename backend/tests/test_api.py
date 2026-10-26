import time
from collections.abc import Callable, Iterator
from typing import Any

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import ec
from fastapi.testclient import TestClient

from engram.api.auth import get_verifier
from engram.api.main import create_app

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
    assert response.json() == {"id": user_id, "display_name": None, "role": "student"}


def test_invites_are_admin_only(
    client: TestClient, make_user: Callable[..., str], database_url: str
) -> None:
    student = make_user()
    response = client.post(
        "/admin/invites", headers=auth(token_for(student)), json={"email": "new@example.com"}
    )
    assert response.status_code == 403
