import pytest
from docling_core.types.doc import DoclingDocument

from engram.ingest.model import Location, ParsedMaterial
from engram.ingest.structure import MAX_WORDS, _levels_from_numbering, _pack
from tests.fixtures import textbook


@pytest.fixture(scope="session")
def parsed(tmp_path_factory: pytest.TempPathFactory) -> ParsedMaterial:
    from engram.ingest.parse import parse

    pdf = textbook.build(tmp_path_factory.mktemp("pdf") / "textbook.pdf")
    return parse(pdf, slides=False)


def test_sections_follow_the_outline(parsed: ParsedMaterial) -> None:
    got = [(s.level, s.title, s.page_start, s.page_end, s.parent) for s in parsed.sections]
    assert got == [
        (1, "Chapter 1 Cells", 1, 2, None),
        (2, "1.1 Cell Structure", 1, 1, 0),
        (2, "1.2 Mitochondria", 1, 2, 0),
        (1, "Chapter 2 Genetics", 3, 3, None),
        (2, "2.1 Inheritance", 3, 3, 3),
    ]
    assert parsed.page_count == 3


def test_figure_is_extracted_with_caption_and_section(parsed: ParsedMaterial) -> None:
    [figure] = parsed.figures
    assert figure.caption == "Figure 1.1 The parts of an animal cell."
    assert figure.section == 1
    assert figure.context == ["Chapter 1 Cells", "1.1 Cell Structure"]
    assert figure.location.page == 1
    assert figure.image_png.startswith(b"\x89PNG")


def test_chunks_carry_section_path_and_locations(parsed: ParsedMaterial) -> None:
    by_section = {c.section: c for c in parsed.chunks if c.kind == "text"}
    mito = by_section[2]
    assert mito.heading_path == ["Chapter 1 Cells", "1.2 Mitochondria"]
    assert mito.content.startswith("Chapter 1 Cells > 1.2 Mitochondria\n\n")
    # The section's text runs from the bottom of page 1 onto page 2.
    assert {loc.page for loc in mito.locations} == {1, 2}
    # Boxes use a top-left origin: the first chunk on a page sits near the top.
    first = parsed.chunks[0].locations[0]
    assert first.page == 1 and first.bbox[1] < 200 and first.bbox[1] < first.bbox[3]


def test_two_column_text_keeps_both_columns(parsed: ParsedMaterial) -> None:
    inheritance = [c for c in parsed.chunks if c.section == 4]
    lefts = {round(loc.bbox[0]) for c in inheritance for loc in c.locations}
    assert len(lefts) == 2  # a box in each column
    assert sum(c.text.count("Offspring") for c in inheritance) == 25


def test_tables_become_their_own_chunks(parsed: ParsedMaterial) -> None:
    [table] = [c for c in parsed.chunks if c.kind == "table"]
    assert "| Mitochondrion" in table.text and table.section == 2


def test_captions_are_not_duplicated_into_body_text(parsed: ParsedMaterial) -> None:
    assert not any("Figure 1.1" in c.text for c in parsed.chunks if c.kind == "text")


def test_levels_from_numbering() -> None:
    titles = ["Chapter 3 Cells", "3.1 Membranes", "3.1.2 Pumps", "Key Terms", "4 Energy", "4.1 ATP"]
    assert _levels_from_numbering(titles) == [1, 2, 3, 4, 1, 2]
    assert _levels_from_numbering(["Introduction", "Methods"]) == [1, 1]


def test_pack_respects_the_word_limit() -> None:
    here = [Location(1, (0, 0, 1, 1))]
    long = " ".join(f"Sentence {i} is here." for i in range(200))  # 800 words
    chunks = list(_pack([("short paragraph", here), (long, here)]))
    assert all(len(text.split()) <= MAX_WORDS for text, _ in chunks)
    assert sum(len(text.split()) for text, _ in chunks) == 2 + 800
    assert chunks[0][0].startswith("short paragraph")


def _doc_with_unlinked_caption() -> DoclingDocument:
    from docling_core.types.doc import (
        BoundingBox,
        CoordOrigin,
        DocItemLabel,
        ImageRef,
        ProvenanceItem,
        Size,
    )
    from PIL import Image

    def prov(top: float, bottom: float, left: float = 72, right: float = 540) -> ProvenanceItem:
        box = BoundingBox(l=left, t=top, r=right, b=bottom, coord_origin=CoordOrigin.TOPLEFT)
        return ProvenanceItem(page_no=1, bbox=box, charspan=(0, 0))

    doc = DoclingDocument(name="unlinked")
    doc.add_page(page_no=1, size=Size(width=612, height=792))
    doc.add_heading("1.1 Cells", prov=prov(72, 90))
    doc.add_text(DocItemLabel.TEXT, "Cells are small.", prov=prov(100, 140))
    image = ImageRef.from_pil(Image.new("RGB", (300, 200), "white"), dpi=72)
    doc.add_picture(image=image, prov=prov(150, 350, 150, 450))
    # Labelled as plain text and not linked to the picture, as Docling sometimes reports it.
    doc.add_text(DocItemLabel.TEXT, "Figure 1.1 A cell.", prov=prov(355, 370))
    doc.add_text(DocItemLabel.TEXT, "Figures help.", prov=prov(380, 400))
    return doc


def test_unlinked_caption_is_attached_to_its_figure() -> None:
    from engram.ingest.structure import OutlineEntry, build

    parsed = build(_doc_with_unlinked_caption(), outline=[OutlineEntry(1, "1.1 Cells", 1)])
    [figure] = parsed.figures
    assert figure.caption == "Figure 1.1 A cell."
    body = " ".join(c.text for c in parsed.chunks)
    assert "Figure 1.1" not in body
    assert "Cells are small." in body and "Figures help." in body  # caption-like rule is strict
