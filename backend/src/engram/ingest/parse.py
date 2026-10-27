"""Runs Docling on an uploaded file. Conversion is CPU-heavy and loads layout models, so the
converter is built once per process and only in the worker."""

from functools import lru_cache
from pathlib import Path

import pypdfium2 as pdfium
from docling.datamodel.base_models import InputFormat
from docling.datamodel.pipeline_options import PdfPipelineOptions
from docling.document_converter import DocumentConverter, PdfFormatOption

from engram.ingest import structure
from engram.ingest.model import ParsedMaterial
from engram.ingest.structure import OutlineEntry


@lru_cache(maxsize=1)
def _converter() -> DocumentConverter:
    # Course PDFs are digital, so OCR stays off; photographed notes go to a vision model.
    options = PdfPipelineOptions(do_ocr=False, generate_picture_images=True, images_scale=2.0)
    return DocumentConverter(
        allowed_formats=[InputFormat.PDF, InputFormat.PPTX],
        format_options={InputFormat.PDF: PdfFormatOption(pipeline_options=options)},
    )


def parse(path: Path, *, slides: bool) -> ParsedMaterial:
    doc = _converter().convert(path).document
    outline = read_outline(path) if path.suffix.lower() == ".pdf" and not slides else []
    return structure.build(doc, outline=outline, slides=slides)


def read_outline(path: Path) -> list[OutlineEntry]:
    """The PDF's bookmark tree, if any, as (level, title, page) in document order."""
    pdf = pdfium.PdfDocument(path)
    try:
        entries = []
        for bookmark in pdf.get_toc():
            dest = bookmark.get_dest()
            title = (bookmark.get_title() or "").strip()
            if dest is None or not title:
                continue
            entries.append(OutlineEntry(bookmark.level + 1, title, dest.get_index() + 1))
        return entries
    finally:
        pdf.close()
