import os
from typing import Any

from openai import OpenAI

from app.tools import Tool, ToolCall, parse_tool_call

from .client import LLMClient
from .openai_tools import to_openai_tool


class OpenAIClient(LLMClient):
    """OpenAI implementation of the provider-independent LLMClient."""

    def __init__(
        self,
        *,
        model: str | None = None,
        temperature: float | None = None,
        system_prompt: str | None = None,
        timeout_seconds: float | None = None,

    ) -> None:
        self._client = OpenAI(
            api_key=os.environ["OPENAI_API_KEY"],
            base_url="https://api.groq.com/openai/v1",
            timeout=timeout_seconds,
            max_retries=0,
        )

        self._model = model or os.getenv(
            "OPENAI_MODEL",
            "openai/gpt-oss-120b",
        )

        self._temperature = (
            temperature
            if temperature is not None
            else float(
                os.getenv(
                    "OPENAI_TEMPERATURE",
                    "0.2",
                )
            )
        )

        self._system_prompt: str | None = system_prompt

    def ask(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
    ) -> str:
        response = self._client.responses.create(
            model=self._model,
            instructions=system_prompt,
            input=user_prompt,
            temperature=self._temperature,
        )

        return response.output_text

    def respond_with_tools(
        self,
        *,
        conversation: list[dict[str, Any]],
        tools: list[Tool],
    ) -> tuple[Any, list[ToolCall]]:
        """Single unified call used by AgentLoop on every iteration.

        Sends the full conversation history and available tools to the
        model, then extracts any tool-call requests from the response.
        """
        response = self._client.responses.create(
            model=self._model,
            instructions=self._system_prompt,
            input=conversation,
            tools=[to_openai_tool(tool) for tool in tools],
            temperature=self._temperature,
        )

        tool_calls: list[ToolCall] = []

        for item in response.output:
            if item.type != "function_call":
                continue

            tool_calls.append(
                parse_tool_call(
                    call_id=item.call_id,
                    name=item.name,
                    raw_arguments=item.arguments,
                )
            )

        return response, tool_calls
