"""Supabase Storage, accessed with the secret key. Buckets are private: browsers only ever
get short-lived signed URLs created here."""

import re
from pathlib import Path
from typing import Any

import httpx

from engram.config import Settings

BUCKET = "materials"


def safe_filename(name: str) -> str:
    """A storage-safe version of an uploaded file's name, keeping its extension."""
    stem, suffix = Path(name).stem, Path(name).suffix.lower()
    stem = re.sub(r"[^A-Za-z0-9._-]+", "-", stem).strip("-") or "file"
    return f"{stem[:80]}{suffix}"


class Storage:
    def __init__(self, settings: Settings, client: httpx.AsyncClient | None = None) -> None:
        secret = settings.supabase_secret_key.get_secret_value()
        self._client = client or httpx.AsyncClient(
            base_url=f"{settings.supabase_url.rstrip('/')}/storage/v1",
            headers={"apikey": secret, "Authorization": f"Bearer {secret}"},
            timeout=httpx.Timeout(30, read=300),
        )

    async def __aenter__(self) -> "Storage":
        return self

    async def __aexit__(self, *exc: object) -> None:
        await self._client.aclose()

    async def download(self, path: str) -> bytes:
        response = await self._client.get(f"/object/{BUCKET}/{path}")
        response.raise_for_status()
        return response.content

    async def upload(self, path: str, data: bytes, content_type: str) -> None:
        response = await self._client.post(
            f"/object/{BUCKET}/{path}",
            content=data,
            headers={"Content-Type": content_type, "x-upsert": "true"},
        )
        response.raise_for_status()

    async def upload_token(self, path: str) -> str:
        """A token that lets a browser upload one file to `path`, without the API in between.
        Cloud Run caps request bodies at 32 MiB, well under a textbook."""
        response = await self._client.post(f"/object/upload/sign/{BUCKET}/{path}")
        response.raise_for_status()
        token: str = response.json()["token"]
        return token

    async def head(self, path: str, length: int) -> tuple[bytes, int] | None:
        """The first `length` bytes of an object and its full size, or None if it's missing."""
        response = await self._client.get(
            f"/object/{BUCKET}/{path}", headers={"Range": f"bytes=0-{length - 1}"}
        )
        if not response.is_success:
            return None
        size = response.headers.get("content-range", "").rpartition("/")[2]
        return response.content[:length], int(size) if size.isdigit() else len(response.content)

    async def remove_prefix(self, prefix: str) -> None:
        """Delete every object under `prefix/` (one level deep)."""
        response = await self._client.post(
            f"/object/list/{BUCKET}", json={"prefix": prefix, "limit": 1000}
        )
        response.raise_for_status()
        names = [f"{prefix}/{item['name']}" for item in response.json() if item.get("id")]
        if names:
            response = await self._client.request(
                "DELETE", f"/object/{BUCKET}", json={"prefixes": names}
            )
            response.raise_for_status()

    async def signed_url(self, path: str, expires_in: int = 3600) -> str:
        response = await self._client.post(
            f"/object/sign/{BUCKET}/{path}", json={"expiresIn": expires_in}
        )
        response.raise_for_status()
        body: dict[str, Any] = response.json()
        return f"{self._client.base_url}{body['signedURL']}"
