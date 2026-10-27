from dataclasses import dataclass, field
from typing import Literal

# [left, top, right, bottom] in PDF points from the page's top-left corner.
BBox = tuple[float, float, float, float]


@dataclass(frozen=True)
class Location:
    page: int  # 1-based
    bbox: BBox


@dataclass
class Section:
    ordinal: int
    level: int  # 1 = chapter
    title: str
    page_start: int
    page_end: int
    parent: int | None = None  # ordinal of the parent section


@dataclass
class Figure:
    ordinal: int
    location: Location
    image_png: bytes
    caption: str | None
    section: int | None
    context: list[str] = field(default_factory=list)  # heading path, for the describer


@dataclass
class Chunk:
    ordinal: int
    kind: Literal["text", "table", "figure", "slide"]
    text: str
    heading_path: list[str]
    locations: list[Location]
    section: int | None
    figure: int | None = None

    @property
    def content(self) -> str:
        """What gets embedded and searched: the text, prefixed with where it sits."""
        if not self.heading_path:
            return self.text
        return " > ".join(self.heading_path) + "\n\n" + self.text


@dataclass
class ParsedMaterial:
    page_count: int
    sections: list[Section]
    figures: list[Figure]
    chunks: list[Chunk]
