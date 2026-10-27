import base64
from collections.abc import AsyncIterator, Iterator
from contextlib import contextmanager
from typing import Final

import anthropic
from anthropic.types import ContentBlockParam, DocumentBlockParam, Message, MessageParam
from pydantic import BaseModel

from engram.llm.base import (
    AnswerEvent,
    Cite,
    Document,
    ImagePart,
    Part,
    ProviderError,
    ProviderUnavailable,
    TextDelta,
    TextPart,
    Turn,
    Usage,
)

# Answers to students' questions favor a quick reply over long deliberation.
CHAT_EFFORT: Final = "low"


class AnthropicProvider:
    """Claude via the Anthropic API. Credentials come from the environment (ANTHROPIC_API_KEY)."""

    name = "anthropic"

    def __init__(self, client: anthropic.AsyncAnthropic | None = None) -> None:
        self._client = client or anthropic.AsyncAnthropic()

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
        with _errors(model):
            response = await self._client.messages.parse(
                model=model,
                max_tokens=max_tokens,
                system=system,
                messages=[{"role": "user", "content": [_content(p) for p in parts]}],
                output_format=schema,
            )
        _count(usage, model, response)
        if response.stop_reason == "refusal":
            raise ProviderError(f"{model} declined the request ({response._request_id})")
        if response.stop_reason == "max_tokens" or response.parsed_output is None:
            raise ProviderError(f"{model} returned no valid output ({response._request_id})")
        return response.parsed_output

    async def cited(
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
        """Native Citations: each document is a plain-text document, so a citation quotes the
        sentences it relies on and names the document by index."""
        docs: list[DocumentBlockParam] = [
            {
                "type": "document",
                "source": {"type": "text", "media_type": "text/plain", "data": d.text},
                "title": d.title,
                "citations": {"enabled": True},
            }
            for d in documents
        ]
        messages = [_turn(t) for t in history]
        messages.append({"role": "user", "content": [*docs, {"type": "text", "text": question}]})
        with _errors(model):
            async with self._client.messages.stream(
                model=model,
                max_tokens=max_tokens,
                system=system,
                messages=messages,
                output_config={"effort": CHAT_EFFORT},
            ) as stream:
                try:
                    async for event in stream:
                        if event.type != "content_block_delta":
                            continue
                        delta = event.delta
                        if delta.type == "text_delta":
                            yield TextDelta(event.index, delta.text)
                        elif (
                            delta.type == "citations_delta"
                            and delta.citation.type == "char_location"
                        ):
                            citation = delta.citation
                            yield Cite(event.index, citation.document_index, citation.cited_text)
                finally:
                    # Billed even when the student leaves before the answer is finished.
                    message: Message | None
                    try:
                        message = stream.current_message_snapshot
                    except AssertionError:  # nothing was received
                        message = None
                    if message is not None:
                        _count(usage, model, message)
        if message is not None and message.stop_reason == "refusal":
            raise ProviderError(f"{model} declined the request ({message._request_id})")


def _turn(turn: Turn) -> MessageParam:
    if turn.role == "user":
        return {"role": "user", "content": turn.text}
    return {"role": "assistant", "content": turn.text}


@contextmanager
def _errors(model: str) -> Iterator[None]:
    try:
        yield
    except (anthropic.AuthenticationError, anthropic.PermissionDeniedError) as exc:
        raise ProviderUnavailable(f"Anthropic rejected the credentials: {exc.message}") from exc
    except anthropic.NotFoundError as exc:
        raise ProviderUnavailable(f"Unknown model {model!r}: {exc.message}") from exc
    except TypeError as exc:
        # The SDK raises TypeError when no API key or profile can be found.
        if "authentication" not in str(exc):
            raise
        raise ProviderUnavailable("No Anthropic credentials: set ANTHROPIC_API_KEY") from exc


def _count(usage: Usage | None, model: str, response: Message) -> None:
    if usage is not None:
        billed = response.usage
        usage.add(
            Usage(
                requests=1,
                input_tokens=billed.input_tokens,
                output_tokens=billed.output_tokens,
                cache_read_input_tokens=billed.cache_read_input_tokens or 0,
                cache_creation_input_tokens=billed.cache_creation_input_tokens or 0,
                models={model},
            )
        )


def _content(part: Part) -> ContentBlockParam:
    match part:
        case TextPart(text):
            return {"type": "text", "text": text}
        case ImagePart(data, media_type):
            return {
                "type": "image",
                "source": {
                    "type": "base64",
                    "media_type": media_type,
                    "data": base64.standard_b64encode(data).decode(),
                },
            }
