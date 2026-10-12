import json
from collections.abc import Callable, Sequence
from time import perf_counter
from typing import Any

from app.llm import (
    AttemptRecord,
    DeadlineExceeded,
    LLMCallFailed,
    LLMClient,
    LLMResponse,
)
from app.llm.types import assistant_message, tool_result_message, user_message
from app.tools import ToolCall, ToolExecutor, ToolRegistry

from .budget import BudgetTracker, RuntimeBudget
from .clock import Clock, MonotonicClock
from .cost import ModelPricing, TokenBudget, UsageTracker
from .history import ExecutionRecord
from .ledger import build_ledger
from .loop_guard import ConsecutiveCounter, LoopGuard, call_fingerprint
from .nudges import (
    EMPTY_ANSWER_NUDGE,
    failure_nudge,
    no_progress_nudge,
    trailing_empty_searches,
    trailing_failures,
)
from .planner import Planner
from .state import AgentState, AgentStatus, Thought
from .trace import TraceRecorder, TraceSink

_MAX_TRACE_THOUGHT_CHARS = 500  # trace is for diagnosis, not a transcript store
_PLAN_HEADER = "Plan (advisory; revise it if observations contradict it):"


class AgentLoop:
    """Orchestrates LLM decisions and tool execution.

    state.conversation is a provider-neutral, JSON-serializable message list.

    Order per iteration
    ───────────────────
    1. wall-clock budget    → TIMEOUT
    2. iteration budget     → MAX_ITERATIONS
    3. LLM call             → LLM_FAILED / TIMEOUT on retry-layer errors
    4. record usage
    5. final answer?        → COMPLETED (accepted even if over token budget)
    6. token budget         → TOKEN_BUDGET_EXCEEDED (before any side effect)

    Then for each requested tool call:
    7. parse_error?         → observation to model; N consecutive → LOOP_DETECTED
    8. loop guard           → LOOP_DETECTED (before execution)
    9. tool execution       → validation (mandatory) → run → observation
    """

    def __init__(
        self,
        client: LLMClient,
        registry: ToolRegistry,
        executor: ToolExecutor,
        max_iterations: int = 10,
        runtime_budget: RuntimeBudget | None = None,
        clock: Clock | None = None,
        loop_guard_factory: Callable[[], LoopGuard] | None = None,
        token_budget: TokenBudget | None = None,
        pricing: ModelPricing | None = None,
        max_consecutive_malformed: int = 3,
        trace: TraceSink | None = None,
        use_plan: bool = False,
        max_plan_steps: int = 6,
        ledger_every: int | None = None,
        failure_nudge_after: int | None = None,
        retry_empty_answer: bool = False,
        no_progress_after: int | None = None,
    ) -> None:
        if (
            token_budget is not None
            and token_budget.max_cost_usd is not None
            and pricing is None
        ):
            raise ValueError(
                "token_budget.max_cost_usd requires pricing to be configured"
            )
        if ledger_every is not None and ledger_every < 1:
            raise ValueError("ledger_every must be >= 1")
        if failure_nudge_after is not None and failure_nudge_after < 1:
            raise ValueError("failure_nudge_after must be >= 1")
        if no_progress_after is not None and no_progress_after < 1:
            raise ValueError("no_progress_after must be >= 1")

        self._client = client
        self._registry = registry
        self._executor = executor
        self._max_iterations = max_iterations
        self._runtime_budget = runtime_budget
        self._clock: Clock = clock or MonotonicClock()
        self._loop_guard_factory = loop_guard_factory
        self._token_budget = token_budget
        self._pricing = pricing
        self._max_consecutive_malformed = max_consecutive_malformed
        self._trace_sink = trace
        self._planner: Planner | None = (
            Planner(client, max_steps=max_plan_steps) if use_plan else None
        )
        self._ledger_every = ledger_every
        self._failure_nudge_after = failure_nudge_after
        self._retry_empty_answer = retry_empty_answer
        self._no_progress_after = no_progress_after

    def run(self, user_prompt: str) -> AgentState:
        state = AgentState(
            conversation=[user_message(user_prompt)],
            usage=UsageTracker(self._pricing),
        )
        trace = (
            TraceRecorder(self._trace_sink)
            if self._trace_sink is not None
            else None
        )
        state.run_id = trace.run_id if trace is not None else None

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
        malformed = ConsecutiveCounter(self._max_consecutive_malformed)
        should_abort = tracker.is_expired if tracker is not None else None

        self._emit(
            trace,
            "run_started",
            prompt=user_prompt,
            max_iterations=self._max_iterations,
        )

        if self._planner is not None:
            self._make_plan(self._planner, state, user_prompt, should_abort, trace)

        while not state.is_finished:
            self._run_iteration(
                state=state,
                tracker=tracker,
                guard=guard,
                malformed=malformed,
                should_abort=should_abort,
                trace=trace,
            )

        self._emit_run_finished(trace, state)
        return state

    def _run_iteration(
        self,
        state: AgentState,
        tracker: BudgetTracker | None,
        guard: LoopGuard | None,
        malformed: ConsecutiveCounter,
        should_abort: Callable[[], bool] | None,
        trace: TraceRecorder | None,
    ) -> None:
        if not self._check_iteration_budget(state, tracker, trace):
            return

        response = self._call_llm(state, should_abort, trace)
        if response is None:
            return

        self._record_thought(response, state)

        if not response.tool_calls:
            self._handle_final_response(response, state, trace)
            return

        if self._token_budget_exhausted(state):
            self._emit(
                trace,
                "guard_triggered",
                guard="token_budget",
                detail=state.error or "",
            )
            return

        self._process_tool_calls(
            list(response.tool_calls), state, guard, malformed, trace
        )
        state.iteration += 1
        self._maybe_add_ledger(state, trace)
        self._maybe_add_failure_nudge(state, trace)
        self._maybe_add_no_progress_nudge(state, trace)

    def _check_iteration_budget(
        self,
        state: AgentState,
        tracker: BudgetTracker | None,
        trace: TraceRecorder | None,
    ) -> bool:
        if tracker is not None and tracker.is_expired():
            state.status = AgentStatus.TIMEOUT
            self._emit(
                trace,
                "guard_triggered",
                guard="timeout",
                detail="wall-clock budget expired",
            )
            return False

        if state.iteration >= self._max_iterations:
            state.status = AgentStatus.MAX_ITERATIONS
            self._emit(
                trace,
                "guard_triggered",
                guard="max_iterations",
                detail=f"limit={self._max_iterations}",
            )
            return False

        return True

    def _call_llm(
        self,
        state: AgentState,
        should_abort: Callable[[], bool] | None,
        trace: TraceRecorder | None,
    ) -> LLMResponse | None:
        started = perf_counter()
        try:
            response = self._client.complete(
                messages=state.conversation,
                tools=self._registry.list(),
                should_abort=should_abort,
            )
        except DeadlineExceeded as exc:
            state.llm_attempts.extend(exc.attempt_log)
            state.status = AgentStatus.TIMEOUT
            self._emit(
                trace,
                "guard_triggered",
                guard="timeout",
                detail="deadline expired while retrying LLM call",
                attempt_log=self._attempts_payload(exc.attempt_log),
            )
            return None
        except LLMCallFailed as exc:
            state.llm_attempts.extend(exc.attempt_log)
            state.status = AgentStatus.LLM_FAILED
            state.error = str(exc)
            self._emit(
                trace,
                "llm_call",
                iteration=state.iteration,
                latency_ms=(perf_counter() - started) * 1000,
                failed=True,
                attempts=len(exc.attempt_log),
                attempt_log=self._attempts_payload(exc.attempt_log),
            )
            return None

        self._emit_llm_call(trace, state.iteration, started, response)
        state.llm_attempts.extend(response.attempts)
        state.usage.record(response.usage)
        state.conversation.append(assistant_message(response))
        return response

    def _handle_final_response(
        self,
        response: LLMResponse,
        state: AgentState,
        trace: TraceRecorder | None = None,
    ) -> None:
        if not response.text.strip():
            if self._retry_empty_answer and state.empty_answer_retries < 1:
                state.empty_answer_retries += 1
                state.conversation.append(user_message(EMPTY_ANSWER_NUDGE))
                self._emit(
                    trace, "empty_answer_nudged", iteration=state.iteration
                )
                state.iteration += 1  # counts against max_iterations
                return
            state.status = AgentStatus.LLM_FAILED
            state.error = "Model returned an empty final answer"
            return

        state.final_response = response.text
        state.status = AgentStatus.COMPLETED

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
        malformed: ConsecutiveCounter,
        trace: TraceRecorder | None = None,
    ) -> None:
        for tool_call in tool_calls:
            if tool_call.parse_error is not None:
                self._record_parse_failure(tool_call, state)
                self._emit(
                    trace, "tool_call", iteration=state.iteration,
                    call_id=tool_call.call_id, tool_name=tool_call.tool_name,
                    arguments={}, success=False,
                    error=f"malformed arguments: {tool_call.parse_error}",
                    duration_ms=0.0, result_chars=0,
                )
                if malformed.failure():
                    state.status = AgentStatus.LOOP_DETECTED
                    state.error = "Too many consecutive malformed tool calls"
                    self._emit(trace, "guard_triggered", guard="malformed_cap",
                               detail=state.error)
                    return
                continue

            malformed.reset()

            if guard is not None:
                fp = call_fingerprint(tool_call.tool_name, tool_call.arguments)
                if guard.record(fp):
                    state.status = AgentStatus.LOOP_DETECTED
                    self._emit(trace, "guard_triggered", guard="loop_guard",
                               detail=f"repeated call blocked: {tool_call.tool_name}")
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
            payload = json.dumps(output, default=str)

            self._emit(
                trace, "tool_call", iteration=state.iteration,
                call_id=tool_call.call_id, tool_name=execution.tool_name,
                arguments=execution.arguments, success=execution.success,
                error=execution.error, duration_ms=execution.duration_ms,
                result_chars=len(payload),
            )

            state.conversation.append(
                tool_result_message(tool_call.call_id, payload)
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
            tool_result_message(
                tool_call.call_id,
                json.dumps({"success": False, "error": error}),
            )
        )

    def _maybe_add_ledger(
        self, state: AgentState, trace: TraceRecorder | None
    ) -> None:
        every = self._ledger_every
        if every is None or state.is_finished:
            return
        if state.iteration % every != 0:
            return
        note = build_ledger(state.history.records())
        if note is None:
            return
        state.conversation.append(user_message(note))
        self._emit(
            trace, "ledger_added", iteration=state.iteration, chars=len(note)
        )

    def _maybe_add_failure_nudge(
        self, state: AgentState, trace: TraceRecorder | None
    ) -> None:
        after = self._failure_nudge_after
        if after is None or state.is_finished:
            return
        records = state.history.records()
        tail = trailing_failures(records)
        tail_len = len(tail)
        if tail_len == 0:
            state.last_nudged_failures = 0
            return
        if tail_len <= state.last_nudged_failures:
            return
        note = failure_nudge(records, threshold=after)
        if note is None:
            return
        state.last_nudged_failures = tail_len
        state.conversation.append(user_message(note))
        self._emit(
            trace,
            "failure_nudged",
            iteration=state.iteration,
            failures=tail_len,
        )

    def _maybe_add_no_progress_nudge(
        self, state: AgentState, trace: TraceRecorder | None
    ) -> None:
        after = self._no_progress_after
        if after is None or state.is_finished:
            return
        streak = len(trailing_empty_searches(state.history.records()))
        if streak == 0:
            state.last_nudged_empty = 0
            return
        if streak <= state.last_nudged_empty:
            return
        note = no_progress_nudge(state.history.records(), threshold=after)
        if note is None:
            return
        state.last_nudged_empty = streak
        state.conversation.append(user_message(note))
        self._emit(
            trace,
            "no_progress_nudged",
            iteration=state.iteration,
            empty_searches=streak,
        )

    @staticmethod
    def _emit(trace: TraceRecorder | None, type_: str, **data: Any) -> None:
        if trace is not None:
            trace.emit(type_, **data)

    @staticmethod
    def _attempts_payload(
        attempts: Sequence[AttemptRecord],
    ) -> list[dict[str, Any]]:
        return [
            {
                "attempt": a.attempt,
                "kind": a.kind.value,
                "delay_s": a.delay_seconds,
                "retry_after_s": a.retry_after_seconds,
                "latency_ms": a.latency_ms,
                "error": a.error[:200],
            }
            for a in attempts
        ]

    def _emit_llm_call(
        self,
        trace: TraceRecorder | None,
        iteration: int,
        started: float,
        response: LLMResponse,
    ) -> None:
        usage = response.usage
        self._emit(
            trace,
            "llm_call",
            iteration=iteration,
            latency_ms=(perf_counter() - started) * 1000,
            input_tokens=usage.input_tokens if usage else None,
            output_tokens=usage.output_tokens if usage else None,
            tool_call_count=len(response.tool_calls),
            thought=self._thought_for_trace(response),
            attempts=len(response.attempts) + 1,
            attempt_log=self._attempts_payload(response.attempts),
        )

    def _emit_run_finished(
        self, trace: TraceRecorder | None, state: AgentState
    ) -> None:
        report = state.usage.report()
        self._emit(
            trace, "run_finished", status=state.status.value,
            iterations=state.iteration, error=state.error,
            total_tokens=report["total_tokens"], cost_usd=report["cost_usd"],
        )

    @staticmethod
    def _record_thought(response: LLMResponse, state: AgentState) -> None:
        text = response.reasoning.strip()
        if text:
            state.thoughts.append(Thought(iteration=state.iteration, text=text))

    @staticmethod
    def _thought_for_trace(response: LLMResponse) -> str | None:
        text = response.reasoning.strip()
        return text[:_MAX_TRACE_THOUGHT_CHARS] if text else None

    def _make_plan(
        self,
        planner: Planner,
        state: AgentState,
        user_prompt: str,
        should_abort: Callable[[], bool] | None,
        trace: TraceRecorder | None,
    ) -> None:
        started = perf_counter()
        try:
            outcome = planner.make(user_prompt, should_abort)
        except (LLMCallFailed, DeadlineExceeded) as exc:
            state.llm_attempts.extend(exc.attempt_log)
            self._emit(
                trace,
                "plan_failed",
                reason=f"{type(exc).__name__}: {str(exc)[:200]}",
                latency_ms=(perf_counter() - started) * 1000,
            )
            return  # advisory: the run continues without a plan

        response = outcome.response
        state.llm_attempts.extend(response.attempts)
        state.usage.record(response.usage)
        latency_ms = (perf_counter() - started) * 1000

        if outcome.plan is None:
            self._emit(
                trace,
                "plan_failed",
                reason=outcome.failure or "",
                latency_ms=latency_ms,
            )
            return

        state.plan = outcome.plan
        state.conversation[0] = user_message(
            f"{user_prompt}\n\n{_PLAN_HEADER}\n{outcome.plan.render()}"
        )
        usage = response.usage
        reasoning = response.reasoning.strip()
        self._emit(
            trace,
            "plan_created",
            steps=[s.description for s in outcome.plan.steps],
            latency_ms=latency_ms,
            input_tokens=usage.input_tokens if usage else None,
            output_tokens=usage.output_tokens if usage else None,
            thought=reasoning[:_MAX_TRACE_THOUGHT_CHARS] or None,
        )

