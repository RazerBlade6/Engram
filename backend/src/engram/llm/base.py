from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from typing import Literal, Protocol

from pydantic import BaseModel

from engram.errors import PermanentError


@dataclass(frozen=True)
class ModelRef:
    """A model at a provider, written `provider:model` in configuration."""

    provider: str
    model: str

    @classmethod
    def parse(cls, value: str) -> "ModelRef":
        provider, sep, model = value.partition(":")
        if not sep or not provider or not model:
            raise ValueError(f"expected 'provider:model', got {value!r}")
        return cls(provider, model)

    def __str__(self) -> str:
        return f"{self.provider}:{self.model}"


@dataclass(frozen=True)
class TextPart:
    text: str


@dataclass(frozen=True)
class ImagePart:
    data: bytes
    media_type: Literal["image/png", "image/jpeg", "image/webp"] = "image/png"


Part = TextPart | ImagePart


@dataclass(frozen=True)
class Document:
    """A passage the answer may cite. Citations point back to it by its position in the list."""

    title: str
    text: str


@dataclass(frozen=True)
class Turn:
    """An earlier message in the conversation, as plain text."""

    role: Literal["user", "assistant"]
    text: str


@dataclass(frozen=True)
class TextDelta:
    """More of the answer. Text arrives in blocks; a block's citations follow its text."""

    block: int
    text: str


@dataclass(frozen=True)
class Cite:
    """The text of `block` is supported by `documents[document]`, which says `quote`."""

    block: int
    document: int
    quote: str


AnswerEvent = TextDelta | Cite


@dataclass
class Usage:
    """Tokens billed across the requests that were given this object. Thinking counts as
    output. A request is counted even when its output is unusable, since it is still billed."""

    requests: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_input_tokens: int = 0
    cache_creation_input_tokens: int = 0
    models: set[str] = field(default_factory=set)

    def add(self, other: "Usage") -> None:
        self.requests += other.requests
        self.input_tokens += other.input_tokens
        self.output_tokens += other.output_tokens
        self.cache_read_input_tokens += other.cache_read_input_tokens
        self.cache_creation_input_tokens += other.cache_creation_input_tokens
        self.models |= other.models


class ProviderError(RuntimeError):
    """The provider declined this request, or returned nothing usable for it."""


class ProviderUnavailable(PermanentError):
    """The provider cannot be used at all: missing or invalid credentials, no access."""


class Provider(Protocol):
    name: str

    async def structured[T: BaseModel](
        self,
        model: str,
        *,
        system: str,
        parts: list[Part],
        schema: type[T],
        max_tokens: int = 4096,
        usage: Usage | None = None,
    ) -> T:
        """Ask for a response that validates against `schema`, adding what the request cost
        to `usage` if given."""
        ...

    def cited(
        self,
        model: str,
        *,
        system: str,
        documents: list[Document],
        history: list[Turn],
        question: str,
        max_tokens: int = 2048,
        usage: Usage | None = None,
    ) -> AsyncIterator[AnswerEvent]:
        """Stream an answer to `question` that cites `documents` where it uses them, adding
        what the request cost to `usage` if given."""
        ...
