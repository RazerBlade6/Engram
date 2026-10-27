"""Page images for the ingestion inspector, rendered from the original PDF with pdfium.

The last few PDFs viewed are kept in memory, so paging through a textbook downloads it once.
pdfium is not thread-safe, so every call into it holds one lock.
"""

import asyncio
import io
import threading
from collections import OrderedDict
from collections.abc import Callable
from typing import Any, Protocol

import pypdfium2 as pdfium

RENDER_WIDTH = 1400  # pixels: sharp at the inspector's width on high-density screens
_pdfium = threading.Lock()


class PageNotFound(LookupError):
    pass


class Downloader(Protocol):
    async def download(self, path: str) -> bytes: ...


class PdfPages:
    def __init__(self, storage: Downloader, *, keep: int = 2) -> None:
        self._storage = storage
        self._keep = keep
        self._files: OrderedDict[str, bytes] = OrderedDict()
        self._loading = asyncio.Lock()

    async def size(self, storage_path: str, page: int) -> tuple[float, float]:
        """Width and height in PDF points, the unit of every stored bounding box."""
        data = await self._file(storage_path)
        width, height = await asyncio.to_thread(_with_page, data, page, lambda p: p.get_size())
        return float(width), float(height)

    async def render(self, storage_path: str, page: int) -> bytes:
        """The page as a JPEG, RENDER_WIDTH pixels wide."""
        data = await self._file(storage_path)
        return await asyncio.to_thread(_with_page, data, page, _jpeg)

    async def _file(self, storage_path: str) -> bytes:
        async with self._loading:
            if storage_path in self._files:
                self._files.move_to_end(storage_path)
            else:
                self._files[storage_path] = await self._storage.download(storage_path)
                while len(self._files) > self._keep:
                    self._files.popitem(last=False)
            return self._files[storage_path]


def _with_page[T](data: bytes, page: int, use: Callable[[Any], T]) -> T:
    with _pdfium:
        pdf = pdfium.PdfDocument(data)
        try:
            if not 1 <= page <= len(pdf):
                raise PageNotFound(page)
            handle = pdf[page - 1]
            try:
                return use(handle)
            finally:
                handle.close()
        finally:
            pdf.close()


def _jpeg(page: Any) -> bytes:
    width, _height = page.get_size()
    image = page.render(scale=RENDER_WIDTH / width).to_pil().convert("RGB")
    out = io.BytesIO()
    image.save(out, format="JPEG", quality=85)
    return out.getvalue()
