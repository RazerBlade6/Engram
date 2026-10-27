import base64

import anthropic
from anthropic.types import ContentBlockParam
from pydantic import BaseModel

from engram.llm.base import ImagePart, Part, ProviderError, ProviderUnavailable, TextPart, Usage


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
        try:
            response = await self._client.messages.parse(
                model=model,
                max_tokens=max_tokens,
                system=system,
                messages=[{"role": "user", "content": [_content(p) for p in parts]}],
                output_format=schema,
            )
        except (anthropic.AuthenticationError, anthropic.PermissionDeniedError) as exc:
            raise ProviderUnavailable(f"Anthropic rejected the credentials: {exc.message}") from exc
        except anthropic.NotFoundError as exc:
            raise ProviderUnavailable(f"Unknown model {model!r}: {exc.message}") from exc
        except TypeError as exc:
            # The SDK raises TypeError when no API key or profile can be found.
            if "authentication" not in str(exc):
                raise
            raise ProviderUnavailable("No Anthropic credentials: set ANTHROPIC_API_KEY") from exc
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
        if response.stop_reason == "refusal":
            raise ProviderError(f"{model} declined the request ({response._request_id})")
        if response.stop_reason == "max_tokens" or response.parsed_output is None:
            raise ProviderError(f"{model} returned no valid output ({response._request_id})")
        return response.parsed_output


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
