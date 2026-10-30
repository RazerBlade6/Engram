from types import SimpleNamespace
from typing import Any

import pytest
from pydantic import BaseModel

from engram.config import Settings
from engram.llm import ImagePart, Job, ModelRef, ProviderError, Router, TextPart, Usage
from engram.llm.anthropic import AnthropicProvider
from engram.llm.base import Cite, Document, TextDelta, Turn


class Answer(BaseModel):
    value: str


class StubMessages:
    def __init__(self, response: Any) -> None:
        self.response = response
        self.calls: list[dict[str, Any]] = []

    async def parse(self, **kwargs: Any) -> Any:
        self.calls.append(kwargs)
        return self.response


def stub_client(**response: Any) -> Any:
    defaults = {"stop_reason": "end_turn", "parsed_output": Answer(value="ok"), "_request_id": "r"}
    return SimpleNamespace(messages=StubMessages(SimpleNamespace(**(defaults | response))))


def test_model_ref_parsing() -> None:
    assert ModelRef.parse("anthropic:claude-haiku-5-5") == ModelRef("anthropic", "claude-haiku-5-5")
    with pytest.raises(ValueError):
        ModelRef.parse("claude-haiku-5-5")


def test_router_resolves_jobs_from_settings() -> None:
    settings = Settings(model_figure_description="anthropic:some-model")
    provider = AnthropicProvider(stub_client())
    router = Router(settings, {"anthropic": provider})
    assert router.provider_for(Job.FIGURE_DESCRIPTION) == (provider, "some-model")
    with pytest.raises(LookupError):
        Router(Settings(model_chat="other:x"), {"anthropic": provider}).provider_for(Job.CHAT)


async def test_anthropic_structured_sends_image_and_text() -> None:
    client = stub_client()
    result = await AnthropicProvider(client).structured(
        "m", system="sys", parts=[ImagePart(b"png"), TextPart("hi")], schema=Answer
    )
    assert result == Answer(value="ok")
    [call] = client.messages.calls
    assert call["output_format"] is Answer and call["system"] == "sys"
    image, text = call["messages"][0]["content"]
    assert image["source"] == {"type": "base64", "media_type": "image/png", "data": "cG5n"}
    assert text == {"type": "text", "text": "hi"}


@pytest.mark.parametrize("response", [{"stop_reason": "refusal"}, {"parsed_output": None}])
async def test_anthropic_structured_raises_on_unusable_output(response: dict[str, Any]) -> None:
    with pytest.raises(ProviderError):
        await AnthropicProvider(stub_client(**response)).structured(
            "m", system="s", parts=[TextPart("x")], schema=Answer
        )


async def test_missing_credentials_are_permanent() -> None:
    from engram.errors import PermanentError

    class NoAuth:
        async def parse(self, **kwargs: Any) -> Any:
            raise TypeError('"Could not resolve authentication method. Expected one of api_key"')

    provider = AnthropicProvider(SimpleNamespace(messages=NoAuth()))  # type: ignore[arg-type]
    with pytest.raises(PermanentError):
        await provider.structured("m", system="s", parts=[TextPart("x")], schema=Answer)


async def test_anthropic_usage_is_counted_even_when_the_output_is_unusable() -> None:
    billed = SimpleNamespace(
        input_tokens=1000,
        output_tokens=200,
        cache_read_input_tokens=None,
        cache_creation_input_tokens=50,
    )
    usage = Usage()
    provider = AnthropicProvider(stub_client(usage=billed))
    await provider.structured("m", system="s", parts=[TextPart("x")], schema=Answer, usage=usage)
    with pytest.raises(ProviderError):
        await AnthropicProvider(stub_client(usage=billed, stop_reason="refusal")).structured(
            "m", system="s", parts=[TextPart("x")], schema=Answer, usage=usage
        )
    assert usage == Usage(2, 2000, 400, 0, 100, {"m"})


class StubStream:
    """Plays back raw stream events, like the SDK's `messages.stream(...)` manager."""

    def __init__(self, events: list[Any], message: Any) -> None:
        self.events = events
        self.current_message_snapshot = message

    async def __aenter__(self) -> "StubStream":
        return self

    async def __aexit__(self, *exc: Any) -> None:
        return None

    def __aiter__(self) -> Any:
        async def play() -> Any:
            for event in self.events:
                yield event

        return play()


async def test_anthropic_cited_streams_text_and_citations() -> None:
    def delta(index: int, **fields: Any) -> Any:
        return SimpleNamespace(
            type="content_block_delta", index=index, delta=SimpleNamespace(**fields)
        )

    citation = SimpleNamespace(type="char_location", document_index=1, cited_text="Water boils.")
    events = [
        SimpleNamespace(type="message_start"),
        delta(1, type="text_delta", text="It boils at 100°C"),
        delta(1, type="citations_delta", citation=citation),
        delta(2, type="text_delta", text="."),
    ]
    billed = SimpleNamespace(
        input_tokens=900,
        output_tokens=60,
        cache_read_input_tokens=None,
        cache_creation_input_tokens=None,
    )
    message = SimpleNamespace(usage=billed, stop_reason="end_turn", _request_id="r")
    calls: list[dict[str, Any]] = []

    def stream(**kwargs: Any) -> StubStream:
        calls.append(kwargs)
        return StubStream(events, message)

    provider = AnthropicProvider(SimpleNamespace(messages=SimpleNamespace(stream=stream)))  # type: ignore[arg-type]
    usage = Usage()
    got = [
        e
        async for e in provider.cited(
            "m",
            system="s",
            documents=[Document("A", "Ice melts."), Document("B", "Water boils.")],
            history=[Turn("user", "Hi"), Turn("assistant", "Hello")],
            question="When does water boil?",
            usage=usage,
        )
    ]
    assert got == [TextDelta(1, "It boils at 100°C"), Cite(1, 1, "Water boils."), TextDelta(2, ".")]
    assert usage == Usage(1, 900, 60, 0, 0, {"m"})
    sent = calls[0]
    assert sent["output_config"] == {"effort": "low"}
    assert [m["role"] for m in sent["messages"]] == ["user", "assistant", "user"]
    documents = sent["messages"][-1]["content"][:2]
    assert all(d["type"] == "document" and d["citations"] == {"enabled": True} for d in documents)
    assert sent["messages"][-1]["content"][-1] == {"type": "text", "text": "When does water boil?"}


def bad_request(message: str) -> Any:
    import anthropic
    import httpx2 as httpx

    response = httpx.Response(
        400, request=httpx.Request("POST", "https://api.anthropic.com/v1/messages")
    )
    body = {"type": "error", "error": {"type": "invalid_request_error", "message": message}}
    return anthropic.BadRequestError(message, response=response, body=body)


async def test_blocked_output_is_a_decline_for_this_request_only() -> None:
    import anthropic

    class Raises:
        def __init__(self, error: Exception) -> None:
            self.error = error

        async def parse(self, **kwargs: Any) -> Any:
            raise self.error

    blocked = Raises(bad_request("Output blocked by content filtering policy"))
    provider = AnthropicProvider(SimpleNamespace(messages=blocked))  # type: ignore[arg-type]
    with pytest.raises(ProviderError):
        await provider.structured("m", system="s", parts=[TextPart("x")], schema=Answer)

    malformed = Raises(bad_request("messages: field required"))
    provider = AnthropicProvider(SimpleNamespace(messages=malformed))  # type: ignore[arg-type]
    with pytest.raises(anthropic.BadRequestError):
        await provider.structured("m", system="s", parts=[TextPart("x")], schema=Answer)
