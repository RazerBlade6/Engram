import httpx

from engram.config import Settings
from engram.storage import Storage


def _storage(settings: Settings) -> Storage:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.host == "host.docker.internal"
        return httpx.Response(200, json={"signedURL": "/object/sign/materials/a/b.pdf?token=t"})

    client = httpx.AsyncClient(
        base_url="http://host.docker.internal:54321/storage/v1",
        transport=httpx.MockTransport(handler),
    )
    return Storage(settings, client)


async def test_signed_links_use_the_address_browsers_reach() -> None:
    settings = Settings(
        supabase_url="http://host.docker.internal:54321",
        supabase_public_url="http://127.0.0.1:54321/",
    )
    url = await _storage(settings).signed_url("a/b.pdf")
    assert url == "http://127.0.0.1:54321/storage/v1/object/sign/materials/a/b.pdf?token=t"


async def test_signed_links_default_to_the_supabase_address() -> None:
    settings = Settings(supabase_url="http://host.docker.internal:54321", supabase_public_url=None)
    url = await _storage(settings).signed_url("a/b.pdf")
    assert url.startswith("http://host.docker.internal:54321/storage/v1/object/sign/")
