from dataclasses import dataclass
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


class ProviderError(RuntimeError):
    """The provider declined this request, or returned nothing usable for it."""


class ProviderUnavailable(PermanentError):
    """The provider cannot be used at all: missing or invalid credentials, no access."""


class Provider(Protocol):
    name: str

    async def structured[T: BaseModel](
        self, model: str, *, system: str, parts: list[Part], schema: type[T]
    ) -> T:
        """Ask for a response that validates against `schema`."""
        ...
