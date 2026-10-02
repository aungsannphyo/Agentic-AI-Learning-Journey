import json
from typing import Any, Protocol

from app.tools import Tool, ToolCall, ToolExecutor, ToolRegistry

from .history import ExecutionRecord
from .state import AgentState, AgentStatus


class ToolCallingClient(Protocol):
    def respond_with_tools(
        self,
        *,
        conversation: list[dict[str, Any]],
        tools: list[Tool],
    ) -> tuple[Any, list[ToolCall]]:
        ...


class AgentLoop:
    """Orchestrates LLM decisions and tool execution."""

    def __init__(
        self,
        client: ToolCallingClient,
        registry: ToolRegistry,
        executor: ToolExecutor,
        max_iterations: int = 10,
    ) -> None:
        self._client = client
        self._registry = registry
        self._executor = executor
        self._max_iterations = max_iterations

    def run(
        self,
        user_prompt: str,
    ) -> AgentState:
        state = AgentState(
            conversation=[
                {
                    "role": "user",
                    "content": user_prompt,
                }
            ]
        )

        while not state.is_finished:
            if state.iteration >= self._max_iterations:
                state.status = AgentStatus.MAX_ITERATIONS
                break

            response, tool_calls = (
                self._client.respond_with_tools(
                    conversation=state.conversation,
                    tools=self._registry.list(),
                )
            )

            state.conversation.extend(
                response.output
            )

            if not tool_calls:
                state.final_response = (
                    response.output_text
                )
                state.status = AgentStatus.COMPLETED
                break

            for tool_call in tool_calls:
                execution = self._executor.execute(
                    tool_name=tool_call.tool_name,
                    arguments=tool_call.arguments,
                )

                state.history.add(
                    ExecutionRecord(
                        tool_name=execution.tool_name,
                        arguments=execution.arguments,
                        success=execution.success,
                        result=execution.result,
                        error=execution.error,
                        duration_ms=execution.duration_ms,
                    )
                )

                output: dict[str, Any]

                if execution.success:
                    output = {
                        "success": True,
                        "result": execution.result,
                    }
                else:
                    output = {
                        "success": False,
                        "error": execution.error,
                    }

                state.conversation.append(
                    {
                        "type": "function_call_output",
                        "call_id": tool_call.call_id,
                        "output": json.dumps(
                            output,
                            default=str,
                        ),
                    }
                )

            state.iteration += 1

        return state
