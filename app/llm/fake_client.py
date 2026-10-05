from dataclasses import dataclass, field
from typing import Any

from app.tools import ToolCall, parse_tool_call

from .client import LLMClient


@dataclass
class FakeResponse:
    output_text: str
    output: list[Any] = field(default_factory=list)
    id: str = "fake-response-123"
    usage: Any = None


class FakeLLMClient(LLMClient):
    """Deterministic LLM implementation for tests."""

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

    def _extract_tool_calls(self, response: FakeResponse) -> list[ToolCall]:
        return [
            parse_tool_call(
                call_id=item.call_id,
                name=item.name,
                raw_arguments=item.arguments,
            )
            for item in response.output
            if item.type == "function_call"
        ]

    def ask(self, *, system_prompt: str, user_prompt: str) -> str:
        self.calls.append(
            {"system_prompt": system_prompt, "user_prompt": user_prompt}
        )
        return self.response

    def respond_with_tools(
        self,
        *,
        conversation: list[dict[str, Any]],
        tools: list[Any],
    ) -> tuple[FakeResponse, list[ToolCall]]:
        self.calls.append(
            {
                "method": "respond_with_tools",
                "conversation": list(conversation),
                "tools": [tool.name for tool in tools],
            }
        )
        if self._response_sequence:
            fake_response = self._response_sequence.pop(0)
        else:
            fake_response = FakeResponse(output_text=self.response)

        return fake_response, self._extract_tool_calls(fake_response)
