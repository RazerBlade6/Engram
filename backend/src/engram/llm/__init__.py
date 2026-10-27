"""Provider-agnostic access to language models.

Jobs (describing a figure, generating cards, answering a question) never name a provider.
Each job resolves to a `ModelRef` from configuration, and the matching `Provider` adapter
makes the call. Which model runs which job is decided by the eval suite; until it exists the
defaults in `engram.config` are provisional.
"""

from engram.llm.base import (
    ImagePart,
    ModelRef,
    Provider,
    ProviderError,
    ProviderUnavailable,
    TextPart,
)
from engram.llm.router import Job, Router

__all__ = [
    "ImagePart",
    "Job",
    "ModelRef",
    "Provider",
    "ProviderError",
    "ProviderUnavailable",
    "Router",
    "TextPart",
]
