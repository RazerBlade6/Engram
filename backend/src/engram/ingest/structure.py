"""Builds the table of contents and the retrieval chunks from a parsed document.

Docling recovers reading order, headings, tables and figures, but reports every PDF heading
at the same level. The hierarchy comes from the PDF's bookmark outline when it has one
(textbooks almost always do), and otherwise from heading numbering ("Chapter 3", "3.2.1").
Each section is then anchored to a position in Docling's reading order, and content belongs
to the section whose anchor most recently precedes it.
"""

import io
import re
from collections.abc import Iterator
from dataclasses import dataclass

from docling_core.types.doc import (
    DocItem,
    DocItemLabel,
    DoclingDocument,
    PictureItem,
    SectionHeaderItem,
    TableItem,
    TextItem,
    TitleItem,
)

from engram.ingest.model import Chunk, Figure, Location, ParsedMaterial, Section

MAX_WORDS = 250  # bge-small reads 512 tokens; leave room for the heading path
MIN_FIGURE_POINTS = 72  # skip icons and logos smaller than an inch on either side
_SENTENCE_END = re.compile(r"(?<=[.!?])\s+")


@dataclass(frozen=True)
class OutlineEntry:
    level: int  # 1-based
    title: str
    page: int  # 1-based


@dataclass
class _Anchor:
    section: Section
    position: int  # index into the document's items


def build(
    doc: DoclingDocument, *, outline: list[OutlineEntry], slides: bool = False
) -> ParsedMaterial:
    items = list(_body_items(doc))
    page_count = max(len(doc.pages), 1)
    anchors = [] if slides else _anchor_sections(items, outline, page_count)
    sections = [a.section for a in anchors]
    figures: list[Figure] = []
    chunks: list[Chunk] = []

    def section_at(position: int) -> Section | None:
        current = None
        for anchor in anchors:
            if anchor.position > position:
                break
            current = anchor.section
        return current

    def path_of(section: Section | None) -> list[str]:
        titles: list[str] = []
        while section is not None:
            titles.append(section.title)
            section = sections[section.parent] if section.parent is not None else None
        return titles[::-1]

    def add_chunk(
        kind: str,
        text: str,
        locations: list[Location],
        section: Section | None,
        figure: int | None = None,
    ) -> None:
        chunks.append(
            Chunk(
                ordinal=len(chunks),
                kind=kind,  # type: ignore[arg-type]
                text=text,
                heading_path=path_of(section),
                locations=locations,
                section=section.ordinal if section else None,
                figure=figure,
            )
        )

    if slides:
        for _page_no, page_items in _by_page(items):
            text = "\n".join(t for _, item in page_items if (t := _text_of(item, doc)))
            if text:
                locations = [loc for _, i in page_items for loc in _locations(i, doc)]
                add_chunk("slide", text, locations, None)
            for _position, item in page_items:
                if isinstance(item, PictureItem):
                    _add_figure(item, doc, item.caption_text(doc) or None, None, [], figures)
        return ParsedMaterial(page_count, sections, figures, chunks)

    captions, claimed = _captions(items, doc)
    buffer: list[tuple[str, list[Location]]] = []
    buffer_section: Section | None = None

    def flush() -> None:
        nonlocal buffer
        for text, locations in _pack(buffer):
            add_chunk("text", text, locations, buffer_section)
        buffer = []

    for position, item in enumerate(items):
        section = section_at(position)
        if section is not buffer_section:
            flush()
            buffer_section = section
        if isinstance(item, SectionHeaderItem | TitleItem) or position in claimed:
            continue
        if isinstance(item, PictureItem):
            flush()
            _add_figure(item, doc, captions.get(position), section, path_of(section), figures)
        elif isinstance(item, TableItem):
            flush()
            table = item.export_to_markdown(doc)
            caption = captions.get(position)
            text = f"{caption}\n\n{table}" if caption else table
            add_chunk("table", text, _locations(item, doc), section)
        elif isinstance(item, TextItem) and item.label != DocItemLabel.CAPTION:
            if item.text.strip():
                buffer.append((item.text.strip(), _locations(item, doc)))
    flush()
    return ParsedMaterial(page_count, sections, figures, chunks)


# Sections ------------------------------------------------------------------------------


def _anchor_sections(
    items: list[DocItem], outline: list[OutlineEntry], page_count: int
) -> list[_Anchor]:
    headers = [
        (position, item)
        for position, item in enumerate(items)
        if isinstance(item, SectionHeaderItem)
    ]
    entries = outline or [
        OutlineEntry(level, item.text.strip(), _page(item))
        for (_, item), level in zip(
            headers, _levels_from_numbering([h.text for _, h in headers]), strict=True
        )
    ]

    anchors: list[_Anchor] = []
    stack: list[Section] = []
    floor = 0  # anchors must follow reading order
    for ordinal, entry in enumerate(entries):
        position = _find_header(headers, entry, floor)
        if position is None:
            position = next(
                (p for p, item in enumerate(items) if p >= floor and _page(item) >= entry.page),
                len(items),
            )
        floor = position
        while stack and stack[-1].level >= entry.level:
            stack.pop()
        section = Section(
            ordinal=ordinal,
            level=entry.level,
            title=entry.title,
            page_start=entry.page,
            page_end=page_count,
            parent=stack[-1].ordinal if stack else None,
        )
        stack.append(section)
        anchors.append(_Anchor(section, position))

    # A section ends where the next section at the same or a higher level begins: on that
    # page if it starts partway down, on the page before if it starts at the top.
    first_on_page: dict[int, int] = {}
    for position, item in enumerate(items):
        first_on_page.setdefault(_page(item), position)
    for i, anchor in enumerate(anchors):
        nxt = next((a for a in anchors[i + 1 :] if a.section.level <= anchor.section.level), None)
        if nxt is None:
            continue
        end = nxt.section.page_start
        if first_on_page.get(end) == nxt.position:
            end -= 1
        anchor.section.page_end = max(anchor.section.page_start, end)
    return anchors


def _find_header(
    headers: list[tuple[int, SectionHeaderItem]], entry: OutlineEntry, floor: int
) -> int | None:
    want = _normalize(entry.title)
    for position, item in headers:
        if position < floor or _page(item) < entry.page:
            continue
        have = _normalize(item.text)
        if have and (have == want or have.startswith(want) or want.startswith(have)):
            return position
    return None


_CHAPTER = re.compile(r"^(chapter|unit|part|module)\s+\w+", re.IGNORECASE)
_NUMBERED = re.compile(r"^(\d+(?:\.\d+)*)\.?\s")


def _levels_from_numbering(titles: Iterator[str] | list[str]) -> list[int]:
    """`Chapter 3` and `3` are level 1, `3.2` is 2, `3.2.1` is 3. An unnumbered heading
    sits one level below the last numbered one (end-of-chapter summaries, key terms)."""
    levels: list[int] = []
    last_numbered = 0
    for title in titles:
        title = title.strip()
        if _CHAPTER.match(title):
            level = last_numbered = 1
        elif m := _NUMBERED.match(title):
            level = last_numbered = m.group(1).count(".") + 1
        else:
            level = last_numbered + 1 if last_numbered else 1
        levels.append(level)
    return levels


def _normalize(text: str) -> str:
    return " ".join(re.findall(r"[a-z0-9]+", text.lower()))


# Content -------------------------------------------------------------------------------


def _pack(
    paragraphs: list[tuple[str, list[Location]]],
) -> Iterator[tuple[str, list[Location]]]:
    """Packs consecutive paragraphs into chunks of at most MAX_WORDS, splitting a paragraph
    that is too long on its own at sentence boundaries (or between words, for text with no
    sentences, such as a glossary)."""
    texts: list[str] = []
    locations: list[Location] = []
    words = 0
    for paragraph, paragraph_locations in paragraphs:
        for piece in _split(paragraph):
            n = len(piece.split())
            if texts and words + n > MAX_WORDS:
                yield "\n\n".join(texts), locations
                texts, locations, words = [], [], 0
            texts.append(piece)
            locations.extend(loc for loc in paragraph_locations if loc not in locations)
            words += n
    if texts:
        yield "\n\n".join(texts), locations


def _split(paragraph: str) -> Iterator[str]:
    if len(paragraph.split()) <= MAX_WORDS:
        yield paragraph
        return
    current: list[str] = []
    count = 0
    for sentence in _pieces(paragraph):
        n = len(sentence.split())
        if current and count + n > MAX_WORDS:
            yield " ".join(current)
            current, count = [], 0
        current.append(sentence)
        count += n
    if current:
        yield " ".join(current)


def _pieces(paragraph: str) -> Iterator[str]:
    for sentence in _SENTENCE_END.split(paragraph):
        words = sentence.split()
        for start in range(0, len(words), MAX_WORDS):
            yield " ".join(words[start : start + MAX_WORDS])


_CAPTION = re.compile(r"^(fig\.|figure|table)\s*\d", re.IGNORECASE)


def _captions(items: list[DocItem], doc: DoclingDocument) -> tuple[dict[int, str], set[int]]:
    """Caption text for each figure and table, by position, and the positions of the text
    items used as captions (left out of the body text).

    Docling links captions to their figure most of the time, but not reliably (it varies even
    between platforms). Without a link, the adjacent text on the same page is taken as the
    caption when it reads like one ("Figure 3.2 ...", "Table 1 ...")."""
    captions: dict[int, str] = {}
    claimed: set[int] = set()
    for position, item in enumerate(items):
        if not isinstance(item, PictureItem | TableItem):
            continue
        if linked := item.caption_text(doc):
            captions[position] = linked
            continue
        for near in (position + 1, position - 1):
            if near in claimed or not 0 <= near < len(items):
                continue
            candidate = items[near]
            if (
                isinstance(candidate, TextItem)
                and not isinstance(candidate, SectionHeaderItem | TitleItem)
                and _page(candidate) == _page(item)
                and _CAPTION.match(candidate.text.strip())
            ):
                captions[position] = candidate.text.strip()
                claimed.add(near)
                break
    return captions, claimed


def _add_figure(
    item: PictureItem,
    doc: DoclingDocument,
    caption: str | None,
    section: Section | None,
    context: list[str],
    figures: list[Figure],
) -> None:
    location = _locations(item, doc)[0]
    left, top, right, bottom = location.bbox
    if right - left < MIN_FIGURE_POINTS or bottom - top < MIN_FIGURE_POINTS:
        return
    image = item.get_image(doc)
    if image is None:
        return
    png = io.BytesIO()
    image.save(png, format="PNG")
    figures.append(
        Figure(
            ordinal=len(figures),
            location=location,
            image_png=png.getvalue(),
            caption=caption,
            section=section.ordinal if section else None,
            context=context,
        )
    )


def _text_of(item: DocItem, doc: DoclingDocument) -> str:
    if isinstance(item, TableItem):
        return item.export_to_markdown(doc)
    if isinstance(item, TextItem):
        return item.text.strip()
    return ""


# Docling helpers -----------------------------------------------------------------------


def _body_items(doc: DoclingDocument) -> Iterator[DocItem]:
    for item, _level in doc.iterate_items():
        if isinstance(item, DocItem) and item.prov:
            yield item


def _page(item: DocItem) -> int:
    return item.prov[0].page_no


def _locations(item: DocItem, doc: DoclingDocument) -> list[Location]:
    """Every region the item occupies: a paragraph can continue into the next column or page."""
    locations = []
    for prov in item.prov:
        height = doc.pages[prov.page_no].size.height
        bbox = prov.bbox.to_top_left_origin(page_height=height)
        locations.append(
            Location(
                page=prov.page_no,
                bbox=(round(bbox.l, 1), round(bbox.t, 1), round(bbox.r, 1), round(bbox.b, 1)),
            )
        )
    return locations


def _by_page(items: list[DocItem]) -> Iterator[tuple[int, list[tuple[int, DocItem]]]]:
    pages: dict[int, list[tuple[int, DocItem]]] = {}
    for position, item in enumerate(items):
        pages.setdefault(_page(item), []).append((position, item))
    yield from sorted(pages.items())
