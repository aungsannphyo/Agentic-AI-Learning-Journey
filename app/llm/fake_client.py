import json
from dataclasses import dataclass, field
from typing import Any, Optional

from app.tools import ToolCall

from .client import LLMClient


@dataclass
class FakeResponse:
    output_text: str
    output: list[Any] = field(default_factory=list)
    id: str = "fake-response-123"


class FakeLLMClient(LLMClient):
    """Deterministic LLM implementation for tests."""

    def __init__(
        self,
        response: str,
        *,
        first_response: Optional["FakeResponse"] = None,
        response_sequence: list["FakeResponse"] | None = None,
    ) -> None:
        self.response = response
        self._first_response = first_response
        # Multi-step sequence for AgentLoop tests.
        # Each call to respond_with_tools pops the next FakeResponse.
        self._response_sequence: list[FakeResponse] = (
            list(response_sequence) if response_sequence else []
        )
        self.calls: list[dict[str, Any]] = []

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _extract_tool_calls(self, response: "FakeResponse") -> list[ToolCall]:
        return [
            ToolCall(
                call_id=item.call_id,
                tool_name=item.name,
                arguments=json.loads(item.arguments),
            )
            for item in response.output
            if item.type == "function_call"
        ]

    # ------------------------------------------------------------------
    # LLMClient interface (simple ask)
    # ------------------------------------------------------------------

    def ask(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
    ) -> str:
        self.calls.append(
            {
                "system_prompt": system_prompt,
                "user_prompt": user_prompt,
            }
        )

        return self.response

    # ------------------------------------------------------------------
    # Single-iteration tool calling (used by run_single_iteration)
    # ------------------------------------------------------------------

    def ask_with_tools(
        self,
        *,
        user_prompt: str,
        tools: list[Any],
    ) -> tuple[FakeResponse, list[Any]]:
        self.calls.append(
            {
                "user_prompt": user_prompt,
                "tools": [tool.name for tool in tools],
            }
        )

        first_response = self._first_response or FakeResponse(
            output_text=self.response,
        )

        return first_response, self._extract_tool_calls(first_response)

    def continue_with_tool_outputs(
        self,
        *,
        conversation: list[dict[str, Any]],
        tools: list[Any],
    ) -> FakeResponse:
        self.calls.append(
            {
                "method": "continue_with_tool_outputs",
                "conversation": conversation,
                "tools": [tool.name for tool in tools],
            }
        )

        return FakeResponse(
            output_text="Final response after tool execution.",
            output=[],
        )

    # ------------------------------------------------------------------
    # Multi-turn method used by AgentLoop
    # ------------------------------------------------------------------

    def respond_with_tools(
        self,
        *,
        conversation: list[dict[str, Any]],
        tools: list[Any],
    ) -> tuple["FakeResponse", list[ToolCall]]:
        """Pop the next FakeResponse from response_sequence.

        When the sequence is exhausted, returns a plain response with
        no tool calls so the loop terminates cleanly.
        """
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
