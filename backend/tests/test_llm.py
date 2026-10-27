from types import SimpleNamespace
from typing import Any

import pytest
from pydantic import BaseModel

from engram.config import Settings
from engram.llm import ImagePart, Job, ModelRef, ProviderError, Router, TextPart, Usage
from engram.llm.anthropic import AnthropicProvider


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
