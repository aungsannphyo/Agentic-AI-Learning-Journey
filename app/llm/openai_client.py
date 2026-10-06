import os
from collections.abc import Callable, Sequence
from typing import Any

from openai import OpenAI

from app.tools import Tool, parse_tool_call

from .openai_tools import to_openai_tool
from .types import LLMResponse, extract_usage


def _function_calls(output: Sequence[Any]) -> list[Any]:
    """Provider output is untrusted; select by structural `type` tag.

    Typed as Any on purpose: the SDK union is wide and tests use
    duck-typed fakes, so narrowing by isinstance would couple both.
    """
    return [i for i in output if getattr(i, "type", None) == "function_call"]


class OpenAIClient:
    """OpenAI Responses API implementation of LLMClient (Groq-compatible)."""

    def __init__(
        self,
        *,
        model: str | None = None,
        temperature: float | None = None,
        system_prompt: str | None = None,
        timeout_seconds: float | None = None,
        sdk_client: Any | None = None,
    ) -> None:
        self._client: Any = sdk_client or OpenAI(
            api_key=os.environ["OPENAI_API_KEY"],
            base_url="https://api.groq.com/openai/v1",
            timeout=timeout_seconds,
            max_retries=0,
        )
        self._model: str = (model or os.getenv("OPENAI_MODEL")) or "openai/gpt-oss-120b"
        self._temperature = (
            temperature
            if temperature is not None
            else float(os.getenv("OPENAI_TEMPERATURE", "0.2"))
        )
        self._system_prompt: str | None = system_prompt

    @staticmethod
    def _to_openai_input(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
        items: list[dict[str, Any]] = []
        for message in messages:
            kind = message["kind"]
            if kind == "user":
                items.append({"role": "user", "content": message["text"]})
            elif kind == "assistant":
                items.extend(message["items"])
            elif kind == "tool_result":
                items.append(
                    {
                        "type": "function_call_output",
                        "call_id": message["call_id"],
                        "output": message["output"],
                    }
                )
            else:
                raise ValueError(f"unknown message kind: {kind}")
        return items

    @staticmethod
    def _dump_item(item: Any) -> dict[str, Any]:
        if isinstance(item, dict):
            return item
        dump = getattr(item, "model_dump", None)
        if callable(dump):
            return dump(mode="json", exclude_none=True)
        raise TypeError(
            f"cannot serialize provider item of type {type(item).__name__}"
        )

    def complete(
        self,
        *,
        messages: list[dict[str, Any]],
        tools: Sequence[Tool],
        should_abort: Callable[[], bool] | None = None,
    ) -> LLMResponse:
        response = self._client.responses.create(
            model=self._model,
            instructions=self._system_prompt,
            input=self._to_openai_input(messages),
            tools=[to_openai_tool(tool) for tool in tools],
            temperature=self._temperature,
        )

        tool_calls = tuple(
            parse_tool_call(
                call_id=item.call_id,
                name=item.name,
                raw_arguments=item.arguments,
            )
            for item in _function_calls(response.output)
        )

        return LLMResponse(
            text=response.output_text,
            tool_calls=tool_calls,
            usage=extract_usage(response),
            assistant_items=tuple(self._dump_item(i) for i in response.output),
        )
