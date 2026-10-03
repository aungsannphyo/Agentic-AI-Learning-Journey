import json
from typing import Any, Protocol

from app.tools import Tool, ToolCall, ToolExecutor, ToolRegistry

from .budget import BudgetTracker
from .history import ExecutionRecord
from .loop_guard import LoopGuard, call_fingerprint
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
    """Orchestrates LLM decisions and tool execution.

    Guard order per iteration
    ─────────────────────────
    1. wall-clock budget  → TIMEOUT
    2. iteration budget   → MAX_ITERATIONS
    3. LLM call
    4. loop-guard check   → LOOP_DETECTED   (before execution)
    5. tool execution
    """

    def __init__(
        self,
        client: ToolCallingClient,
        registry: ToolRegistry,
        executor: ToolExecutor,
        max_iterations: int = 10,
        budget: BudgetTracker | None = None,
        loop_guard: LoopGuard | None = None,
    ) -> None:
        self._client = client
        self._registry = registry
        self._executor = executor
        self._max_iterations = max_iterations
        self._budget = budget
        self._loop_guard = loop_guard

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
            # ── Guard 1: wall-clock budget ───────────────────────────
            if (
                self._budget is not None
                and self._budget.is_expired()
            ):
                state.status = AgentStatus.TIMEOUT
                break

            # ── Guard 2: iteration budget ────────────────────────────
            if state.iteration >= self._max_iterations:
                state.status = AgentStatus.MAX_ITERATIONS
                break

            # ── LLM call ─────────────────────────────────────────────
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

            self._process_tool_calls(tool_calls, state)

            state.iteration += 1

        return state

    def _process_tool_calls(
        self,
        tool_calls: list[ToolCall],
        state: AgentState,
    ) -> None:
        """Execute each tool call and append its output to the conversation.

        Mutates *state* in-place. Stops early if loop detection fires.
        """
        for tool_call in tool_calls:
            # ── Guard 3: loop detection (before execution) ────────
            if self._loop_guard is not None:
                fp = call_fingerprint(
                    tool_call.tool_name,
                    tool_call.arguments,
                )
                if self._loop_guard.record(fp):
                    state.status = AgentStatus.LOOP_DETECTED
                    return

            if state.is_finished:
                return

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

            output: dict[str, Any] = (
                {"success": True, "result": execution.result}
                if execution.success
                else {"success": False, "error": execution.error}
            )

            state.conversation.append(
                {
                    "type": "function_call_output",
                    "call_id": tool_call.call_id,
                    "output": json.dumps(output, default=str),
                }
            )
