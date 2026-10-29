"""The Storage client for request handlers, shared by the routes that add or remove files."""

from typing import Annotated

from fastapi import Depends, Request

from engram.storage import Storage


def get_storage(request: Request) -> Storage:
    storage: Storage = request.app.state.storage
    return storage


Files = Annotated[Storage, Depends(get_storage)]
