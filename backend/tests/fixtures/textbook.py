"""Builds a small synthetic textbook PDF for ingestion tests.

Two chapters with numbered sections, a bookmark outline, a two-column page, a labelled
diagram and a table: the layouts that naive text extraction gets wrong.
"""

import io
from pathlib import Path

from PIL import Image, ImageDraw
from reportlab.lib.pagesizes import LETTER
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import (
    BaseDocTemplate,
    Frame,
    NextPageTemplate,
    PageBreak,
    PageTemplate,
    Paragraph,
    Spacer,
    Table,
)
from reportlab.platypus import (
    Image as RLImage,
)

LOREM = (
    "Cells are the basic unit of life. Every organism is made of one or more cells, and "
    "each cell carries out the chemical reactions that keep it alive. "
)
MITOCHONDRIA = (
    "The mitochondrion converts the energy stored in glucose into ATP through cellular "
    "respiration. Cells with high energy demands, such as muscle cells, contain many of them. "
)


def diagram_png() -> bytes:
    image = Image.new("RGB", (600, 400), "white")
    draw = ImageDraw.Draw(image)
    draw.ellipse((40, 40, 560, 360), outline="black", width=6)
    draw.ellipse((230, 140, 370, 260), outline="black", width=6, fill="#dddddd")
    for xy, label in (
        ((250, 190), "Nucleus"),
        ((60, 20), "Cell membrane"),
        ((380, 300), "Cytoplasm"),
    ):
        draw.text(xy, label, fill="black", font_size=28)
    out = io.BytesIO()
    image.save(out, format="PNG")
    return out.getvalue()


class _Doc(BaseDocTemplate):
    """Adds a PDF bookmark for every heading, nested by level."""

    def afterFlowable(self, flowable: object) -> None:
        level = getattr(flowable, "outline_level", None)
        if level is None:
            return
        text = flowable.getPlainText()  # type: ignore[attr-defined]
        key = f"h{id(flowable)}"
        self.canv.bookmarkPage(key)
        self.canv.addOutlineEntry(text, key, level=level)


def build(path: Path) -> Path:
    styles = getSampleStyleSheet()
    body = styles["BodyText"]
    body.fontSize = 11
    body.leading = 15

    def heading(text: str, level: int) -> Paragraph:
        p = Paragraph(text, styles["Heading1" if level == 0 else "Heading2"])
        p.outline_level = level  # type: ignore[attr-defined]
        return p

    doc = _Doc(str(path), pagesize=LETTER, title="Introductory Biology")
    width, height = LETTER
    margin = inch
    single = Frame(margin, margin, width - 2 * margin, height - 2 * margin, id="single")
    gap = 0.3 * inch
    col = (width - 2 * margin - gap) / 2
    left = Frame(margin, margin, col, height - 2 * margin, id="left")
    right = Frame(margin + col + gap, margin, col, height - 2 * margin, id="right")
    doc.addPageTemplates([PageTemplate("one", [single]), PageTemplate("two", [left, right])])

    story: list[object] = [
        heading("Chapter 1 Cells", 0),
        Paragraph(LOREM * 4, body),
        heading("1.1 Cell Structure", 1),
        Paragraph(LOREM * 3, body),
        RLImage(io.BytesIO(diagram_png()), width=4 * inch, height=2.67 * inch),
        Paragraph("Figure 1.1 The parts of an animal cell.", styles["Italic"]),
        heading("1.2 Mitochondria", 1),
        Paragraph(MITOCHONDRIA * 5, body),
        Table(
            [["Organelle", "Function"], ["Nucleus", "Stores DNA"], ["Mitochondrion", "Makes ATP"]],
            style=[("GRID", (0, 0), (-1, -1), 0.5, "black")],
        ),
        NextPageTemplate("two"),
        PageBreak(),
        heading("Chapter 2 Genetics", 0),
        Paragraph(("Genes are segments of DNA that encode proteins. " * 12), body),
        heading("2.1 Inheritance", 1),
        Paragraph(("Offspring inherit one allele of each gene from each parent. " * 25), body),
        Spacer(1, 12),
    ]
    doc.build(story)
    return path


if __name__ == "__main__":
    import sys

    print(build(Path(sys.argv[1] if len(sys.argv) > 1 else "textbook.pdf")))
