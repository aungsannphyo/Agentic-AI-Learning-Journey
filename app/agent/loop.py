import json
from collections.abc import Callable
from typing import Any, Protocol

from app.tools import Tool, ToolCall, ToolExecutor, ToolRegistry

from .budget import BudgetTracker, RuntimeBudget
from .clock import Clock, MonotonicClock
from .cost import ModelPricing, TokenBudget, UsageTracker
from .history import ExecutionRecord
from .loop_guard import LoopGuard, call_fingerprint
from .resilient_client import DeadlineExceeded, LLMCallFailed
from .state import AgentState, AgentStatus
from .usage import extract_usage


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
    1. wall-clock budget   → TIMEOUT
    2. iteration budget    → MAX_ITERATIONS
    3. LLM call
    4. record usage
    5. final answer?       → COMPLETED (accepted even if over token budget)
    6. token budget        → TOKEN_BUDGET_EXCEEDED (before any side effect)
    7. loop-guard check    → LOOP_DETECTED (before execution)
    8. tool execution
    """

    def __init__(
        self,
        client: ToolCallingClient,
        registry: ToolRegistry,
        executor: ToolExecutor,
        max_iterations: int = 10,
        runtime_budget: RuntimeBudget | None = None,
        clock: Clock | None = None,
        loop_guard_factory: Callable[[], LoopGuard] | None = None,
        token_budget: TokenBudget | None = None,
        pricing: ModelPricing | None = None,
    ) -> None:
        if (
            token_budget is not None
            and token_budget.max_cost_usd is not None
            and pricing is None
        ):
            raise ValueError(
                "token_budget.max_cost_usd requires pricing to be configured"
            )

        self._client = client
        self._registry = registry
        self._executor = executor
        self._max_iterations = max_iterations
        self._runtime_budget = runtime_budget
        self._clock: Clock = clock or MonotonicClock()
        self._loop_guard_factory = loop_guard_factory
        self._token_budget = token_budget
        self._pricing = pricing

    def run(self, user_prompt: str) -> AgentState:
        state = AgentState(
            conversation=[{"role": "user", "content": user_prompt}],
            usage=UsageTracker(self._pricing),
        )

        tracker = (
            BudgetTracker(self._runtime_budget, self._clock)
            if self._runtime_budget is not None
            else None
        )
        guard = (
            self._loop_guard_factory()
            if self._loop_guard_factory is not None
            else None
        )

        set_deadline = getattr(self._client, "set_deadline_check", None)
        if callable(set_deadline):
            set_deadline(tracker.is_expired if tracker is not None else None)

        while not state.is_finished:
            if tracker is not None and tracker.is_expired():
                state.status = AgentStatus.TIMEOUT
                break

            if state.iteration >= self._max_iterations:
                state.status = AgentStatus.MAX_ITERATIONS
                break
            try:
                response, tool_calls = self._client.respond_with_tools(
                    conversation=state.conversation,
                    tools=self._registry.list(),
                )
            except DeadlineExceeded:
                state.status = AgentStatus.TIMEOUT
                break
            except LLMCallFailed as exc:
                state.status = AgentStatus.LLM_FAILED
                state.error = str(exc)
                break

            state.usage.record(extract_usage(response))
            state.conversation.extend(response.output)

            if not tool_calls:
                state.final_response = response.output_text
                state.status = AgentStatus.COMPLETED
                break

            if self._token_budget_exhausted(state):
                break

            self._process_tool_calls(tool_calls, state, guard)

            state.iteration += 1

        return state

    def _token_budget_exhausted(self, state: AgentState) -> bool:
        if self._token_budget is None:
            return False

        reason = state.usage.exceeded(self._token_budget)
        if reason is None:
            return False

        state.status = AgentStatus.TOKEN_BUDGET_EXCEEDED
        state.error = f"Token budget exceeded: {reason}"
        return True

    def _process_tool_calls(
        self,
        tool_calls: list[ToolCall],
        state: AgentState,
        guard: LoopGuard | None,
    ) -> None:
        for tool_call in tool_calls:
            if tool_call.parse_error is not None:
                self._record_parse_failure(tool_call, state)
                continue

            if guard is not None:
                fp = call_fingerprint(tool_call.tool_name, tool_call.arguments)
                if guard.record(fp):
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

    def _record_parse_failure(self, tool_call: ToolCall, state: AgentState) -> None:
        error = f"Malformed tool call arguments: {tool_call.parse_error}"

        state.history.add(
            ExecutionRecord(
                tool_name=tool_call.tool_name,
                arguments={},
                success=False,
                result=None,
                error=error,
                duration_ms=0.0,
            )
        )
        state.conversation.append(
            {
                "type": "function_call_output",
                "call_id": tool_call.call_id,
                "output": json.dumps({"success": False, "error": error}),
            }
        )
