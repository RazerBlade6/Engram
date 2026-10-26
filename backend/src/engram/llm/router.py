from enum import StrEnum

from engram.config import Settings
from engram.llm.base import ModelRef, Provider


class Job(StrEnum):
    FIGURE_DESCRIPTION = "figure_description"
    CARD_GENERATION = "card_generation"
    CHAT = "chat"
    GRADING = "grading"


class Router:
    """Resolves each job to a model and the provider adapter that serves it."""

    def __init__(self, settings: Settings, providers: dict[str, Provider] | None = None) -> None:
        self._models = {job: ModelRef.parse(getattr(settings, f"model_{job}")) for job in Job}
        self._providers = providers if providers is not None else _default_providers()

    def model_for(self, job: Job) -> ModelRef:
        return self._models[job]

    def provider_for(self, job: Job) -> tuple[Provider, str]:
        ref = self._models[job]
        provider = self._providers.get(ref.provider)
        if provider is None:
            raise LookupError(f"no adapter for provider {ref.provider!r} (job {job})")
        return provider, ref.model


def _default_providers() -> dict[str, Provider]:
    from engram.llm.anthropic import AnthropicProvider

    return {"anthropic": AnthropicProvider()}
