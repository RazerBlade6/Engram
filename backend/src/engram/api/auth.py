"""Verifies Supabase access tokens.

Supabase signs access tokens with asymmetric keys published at the project's JWKS endpoint,
so the API verifies them locally without a round trip to Supabase on every request.
"""

from dataclasses import dataclass
from typing import Annotated, Any

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from engram.config import Settings, get_settings

_bearer = HTTPBearer(auto_error=False)


@dataclass(frozen=True)
class User:
    id: str
    claims: dict[str, Any]


class TokenVerifier:
    def __init__(self, supabase_url: str, issuer: str | None = None) -> None:
        auth_url = f"{supabase_url.rstrip('/')}/auth/v1"
        self.issuer = issuer or auth_url
        self._jwks = jwt.PyJWKClient(f"{auth_url}/.well-known/jwks.json", cache_keys=True)

    def verify(self, token: str) -> dict[str, Any]:
        key = self._jwks.get_signing_key_from_jwt(token)
        claims: dict[str, Any] = jwt.decode(
            token,
            key,
            algorithms=["ES256", "RS256"],
            audience="authenticated",
            issuer=self.issuer,
            options={"require": ["exp", "sub", "role"]},
        )
        return claims


_verifier: TokenVerifier | None = None


def get_verifier(settings: Annotated[Settings, Depends(get_settings)]) -> TokenVerifier:
    global _verifier
    if _verifier is None:
        _verifier = TokenVerifier(settings.supabase_url, settings.supabase_jwt_issuer)
    return _verifier


def current_user(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
    verifier: Annotated[TokenVerifier, Depends(get_verifier)],
) -> User:
    unauthorized = HTTPException(
        status.HTTP_401_UNAUTHORIZED,
        "Not signed in",
        headers={"WWW-Authenticate": "Bearer"},
    )
    if credentials is None:
        raise unauthorized
    try:
        claims = verifier.verify(credentials.credentials)
    except jwt.PyJWTError as exc:
        raise unauthorized from exc
    if claims.get("role") != "authenticated":
        raise unauthorized
    return User(id=claims["sub"], claims=claims)


CurrentUser = Annotated[User, Depends(current_user)]
