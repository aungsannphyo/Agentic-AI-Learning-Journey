import json
from types import SimpleNamespace
from typing import Any

from app.llm import FakeResponse, LLMResponse


class SdkItem:
    """Fake SDK output item that serializes like a pydantic object."""

    def __init__(self, **data) -> None:
        self._data = data
        for k, v in data.items():
            setattr(self, k, v)

    def model_dump(self, **_kw):
        return dict(self._data)


def llm_response(text: str = "ok") -> LLMResponse:
    return LLMResponse(text=text, tool_calls=(), usage=None)


def tool_outputs(messages: list[dict]) -> list[dict]:
    """Parsed outputs of all tool_result messages."""
    return [
        json.loads(m["output"])
        for m in messages
        if m.get("kind") == "tool_result"
    ]


def usage(i: int = 1, o: int = 1) -> SimpleNamespace:
    return SimpleNamespace(input_tokens=i, output_tokens=o)


def tool_call_response(
    call_id: str, name: str, arguments: dict[str, Any] | str
) -> FakeResponse:
    raw = arguments if isinstance(arguments, str) else json.dumps(arguments)
    return FakeResponse(
        output_text="",
        output=[
            SimpleNamespace(
                type="function_call", call_id=call_id, name=name, arguments=raw
            )
        ],
        usage=usage(),
    )


def final_response(text: str = "done") -> FakeResponse:
    return FakeResponse(output_text=text, output=[], usage=usage())
