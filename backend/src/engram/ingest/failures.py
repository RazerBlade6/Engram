"""Files Engram can tell it will never read, however often it tries. Each carries a reason the
course page explains to the student (the `material_failure` type)."""

from typing import Literal

from engram.errors import PermanentError

Reason = Literal["no_text", "protected", "damaged"]

# Below this many characters of text a page, a textbook is taken to be scanned pages: OCR is
# off (`engram.ingest.parse`), so there is nothing to read. A digital page carries thousands.
MIN_CHARS_PER_PAGE = 20


class Unreadable(PermanentError):
    def __init__(self, reason: Reason, detail: str) -> None:
        super().__init__(detail)
        self.reason: Reason = reason
