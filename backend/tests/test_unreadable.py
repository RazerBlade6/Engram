"""Files Engram can tell it will never read: each fails with its reason, before Docling runs."""

import zipfile
from pathlib import Path

import pypdfium2 as pdfium
import pytest
from reportlab.lib.pdfencrypt import StandardEncryption
from reportlab.pdfgen import canvas

from engram.ingest.failures import Unreadable
from engram.ingest.parse import check_pdf, parse
from tests.fixtures import textbook


def reason(path: Path, *, textbook: bool = True) -> str | None:
    try:
        check_pdf(path, textbook=textbook)
    except Unreadable as exc:
        return exc.reason
    return None


def scanned(tmp_path: Path) -> Path:
    """The fixture textbook with every page turned into a picture, as a scanner makes it."""
    pdf = pdfium.PdfDocument(textbook.build(tmp_path / "text.pdf"))
    pages = [pdf[i].render(scale=1).to_pil().convert("RGB") for i in range(len(pdf))]
    path = tmp_path / "scanned.pdf"
    pages[0].save(path, save_all=True, append_images=pages[1:])
    return path


def test_a_digital_textbook_passes(tmp_path: Path) -> None:
    assert reason(textbook.build(tmp_path / "text.pdf")) is None


def test_a_scanned_textbook_has_no_text(tmp_path: Path) -> None:
    path = scanned(tmp_path)
    assert reason(path) == "no_text"
    # Slides are let through: a deck exported as pictures still has figures to describe.
    assert reason(path, textbook=False) is None


def test_a_password_is_protected_but_permissions_alone_are_not(tmp_path: Path) -> None:
    locked = canvas.Canvas(str(tmp_path / "locked.pdf"), encrypt="secret")
    locked.drawString(72, 720, "Cells are small. " * 20)
    locked.save()
    assert reason(tmp_path / "locked.pdf") == "protected"

    # Opens without a password; only printing is restricted.
    limited = canvas.Canvas(
        str(tmp_path / "limited.pdf"),
        encrypt=StandardEncryption("", ownerPassword="owner", canPrint=0),
    )
    limited.drawString(72, 720, "Cells are small. " * 20)
    limited.save()
    assert reason(tmp_path / "limited.pdf") is None


def test_a_broken_pdf_is_damaged(tmp_path: Path) -> None:
    path = tmp_path / "broken.pdf"
    path.write_bytes(b"%PDF-1.4\n%%EOF\n")
    assert reason(path) == "damaged"


def test_a_zip_that_isnt_a_presentation_is_damaged(tmp_path: Path) -> None:
    path = tmp_path / "deck.pptx"
    with zipfile.ZipFile(path, "w") as z:
        z.writestr("notes.txt", "not a presentation")
    with pytest.raises(Unreadable) as raised:
        parse(path, slides=True)
    assert raised.value.reason == "damaged"
