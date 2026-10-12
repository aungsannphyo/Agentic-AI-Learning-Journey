from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from typing import Any

from app.tools import parse_tool_call

from .reasoning import extract_reasoning
from .types import LLMResponse, extract_usage


@dataclass
class FakeResponse:
    output_text: str
    output: list[Any] = field(default_factory=list)
    id: str = "fake-response-123"
    usage: Any = None


def _item_to_dict(item: Any) -> dict[str, Any]:
    if isinstance(item, dict):
        return item
    return {
        key: getattr(item, key)
        for key in ("type", "call_id", "name", "arguments")
        if hasattr(item, key)
    }


class FakeLLMClient:
    """Deterministic LLMClient for tests."""

    def __init__(
        self,
        response: str,
        *,
        response_sequence: list[FakeResponse] | None = None,
    ) -> None:
        self.response = response
        self._response_sequence: list[FakeResponse] = (
            list(response_sequence) if response_sequence else []
        )
        self.calls: list[dict[str, Any]] = []
        self.output_schemas: list[dict[str, Any] | None] = []

    def complete(
        self,
        *,
        messages: list[dict[str, Any]],
        tools: Sequence[Any],
        should_abort: Callable[[], bool] | None = None,
        output_schema: dict[str, Any] | None = None,
    ) -> LLMResponse:
        self.output_schemas.append(output_schema)
        self.calls.append(
            {
                "method": "complete",
                "messages": [dict(m) for m in messages],
                "tools": [t.name for t in tools],
            }
        )
        fake = (
            self._response_sequence.pop(0)
            if self._response_sequence
            else FakeResponse(output_text=self.response)
        )

        def _get(item: Any, key: str) -> Any:
            return item.get(key) if isinstance(item, dict) else getattr(item, key, None)

        tool_calls = tuple(
            parse_tool_call(
                call_id=_get(item, "call_id"),
                name=_get(item, "name"),
                raw_arguments=_get(item, "arguments"),
            )
            for item in fake.output
            if _get(item, "type") == "function_call"
        )
        items = tuple(_item_to_dict(i) for i in fake.output)
        return LLMResponse(
            text=fake.output_text,
            tool_calls=tool_calls,
            usage=extract_usage(fake),
            assistant_items=items,
            reasoning=extract_reasoning(items),
        )
