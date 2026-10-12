# Agent Runtime — Agent Runtime & Control Layer Snapshot (`app/agent/`)

AgentLoop orchestration, upfront planning (`Planner`), evidence ledger, reactive nudges (`nudges.py`), LoopGuard, ConsecutiveCounter, wall-clock & token budgets, state models, and structured tracing engine.

**Files count**: 15 files | **Active status**: 278 passed, 3 xfailed, ruff/mypy clean

## ဖိုင်များ မာတိကာ (Table of Contents)

- [`app/agent/__init__.py`](#appagentinitpy)
- [`app/agent/budget.py`](#appagentbudgetpy)
- [`app/agent/clock.py`](#appagentclockpy)
- [`app/agent/cost.py`](#appagentcostpy)
- [`app/agent/history.py`](#appagenthistorypy)
- [`app/agent/ledger.py`](#appagentledgerpy)
- [`app/agent/loop_guard.py`](#appagentloopguardpy)
- [`app/agent/loop.py`](#appagentlooppy)
- [`app/agent/nudges.py`](#appagentnudgespy)
- [`app/agent/plan.py`](#appagentplanpy)
- [`app/agent/plan_parsing.py`](#appagentplanparsingpy)
- [`app/agent/planner.py`](#appagentplannerpy)
- [`app/agent/prompts.py`](#appagentpromptspy)
- [`app/agent/state.py`](#appagentstatepy)
- [`app/agent/trace.py`](#appagenttracepy)

---

### `app/agent/__init__.py` <a id="appagentinitpy"></a>

```python
from .budget import BudgetTracker, RuntimeBudget
from .clock import Clock, MonotonicClock
from .cost import ModelPricing, TokenBudget, UsageTracker
from .history import ExecutionHistory, ExecutionRecord
from .ledger import build_ledger
from .loop import AgentLoop
from .loop_guard import ConsecutiveCounter, LoopGuard, call_fingerprint
from .prompts import PLANNER_V1, PROMPTS, Prompt, get_prompt
from .state import AgentState, AgentStatus, Thought
from .trace import InMemorySink, JsonlFileSink, TraceEvent, TraceRecorder, TraceSink

__all__ = [
    "PLANNER_V1",
    "PROMPTS",
    "AgentLoop",
    "AgentState",
    "AgentStatus",
    "BudgetTracker",
    "Clock",
    "ConsecutiveCounter",
    "ExecutionHistory",
    "ExecutionRecord",
    "InMemorySink",
    "JsonlFileSink",
    "LoopGuard",
    "ModelPricing",
    "MonotonicClock",
    "Prompt",
    "RuntimeBudget",
    "Thought",
    "TokenBudget",
    "TraceEvent",
    "TraceRecorder",
    "TraceSink",
    "UsageTracker",
    "build_ledger",
    "call_fingerprint",
    "get_prompt",
]
```

---

### `app/agent/budget.py` <a id="appagentbudgetpy"></a>

```python
from dataclasses import dataclass

from .clock import Clock


@dataclass(frozen=True)
class RuntimeBudget:
    max_wall_time_seconds: float = 60.0
    per_call_timeout_seconds: float = 30.0

    def __post_init__(self) -> None:
        if self.max_wall_time_seconds <= 0:
            raise ValueError("max_wall_time_seconds must be > 0")

        if self.per_call_timeout_seconds <= 0:
            raise ValueError("per_call_timeout_seconds must be > 0")


class BudgetTracker:
    def __init__(
        self,
        budget: RuntimeBudget,
        clock: Clock,
    ) -> None:
        self._budget = budget
        self._clock = clock
        self._started_at = clock.now()

    def elapsed_seconds(self) -> float:
        return (
            self._clock.now()
            - self._started_at
        )

    def is_expired(self) -> bool:
        return (
            self.elapsed_seconds()
            >= self._budget.max_wall_time_seconds
        )
```

---

### `app/agent/clock.py` <a id="appagentclockpy"></a>

```python
from time import monotonic
from typing import Protocol


class Clock(Protocol):
    def now(self) -> float:
        ...


class MonotonicClock:
    def now(self) -> float:
        return monotonic()
```

---

### `app/agent/cost.py` <a id="appagentcostpy"></a>

```python
from dataclasses import dataclass
from typing import Any

from app.llm.types import Usage


@dataclass(frozen=True)
class ModelPricing:
    """USD per 1M tokens. Supplied via config, never hardcoded."""

    input_usd_per_mtok: float
    output_usd_per_mtok: float

    def __post_init__(self) -> None:
        if self.input_usd_per_mtok < 0 or self.output_usd_per_mtok < 0:
            raise ValueError("pricing must be >= 0")

    def cost_usd(self, usage: Usage) -> float:
        return (
            usage.input_tokens * self.input_usd_per_mtok
            + usage.output_tokens * self.output_usd_per_mtok
        ) / 1_000_000


@dataclass(frozen=True)
class TokenBudget:
    max_total_tokens: int | None = None
    max_cost_usd: float | None = None

    def __post_init__(self) -> None:
        if self.max_total_tokens is not None and self.max_total_tokens < 1:
            raise ValueError("max_total_tokens must be >= 1")
        if self.max_cost_usd is not None and self.max_cost_usd <= 0:
            raise ValueError("max_cost_usd must be > 0")


@dataclass(frozen=True)
class UsageRecord:
    call_index: int  # 1-based
    usage: Usage | None  # None = provider did not report


class UsageTracker:
    """Accumulates per-call usage for a single agent run."""

    def __init__(self, pricing: ModelPricing | None = None) -> None:
        self._pricing = pricing
        self._records: list[UsageRecord] = []

    def record(self, usage: Usage | None) -> None:
        self._records.append(
            UsageRecord(call_index=len(self._records) + 1, usage=usage)
        )

    @property
    def calls(self) -> int:
        return len(self._records)

    @property
    def unreported_calls(self) -> int:
        return sum(1 for r in self._records if r.usage is None)

    @property
    def total(self) -> Usage:
        total = Usage()
        for record in self._records:
            if record.usage is not None:
                total = total + record.usage
        return total

    def cost_usd(self) -> float | None:
        if self._pricing is None:
            return None
        return self._pricing.cost_usd(self.total)

    def exceeded(self, budget: TokenBudget) -> str | None:
        """Return the reason the budget is exhausted, or None."""
        if self.unreported_calls:
            return "usage_unreported"  # fail closed

        if (
            budget.max_total_tokens is not None
            and self.total.total_tokens >= budget.max_total_tokens
        ):
            return "max_total_tokens"

        cost = self.cost_usd()
        if (
            budget.max_cost_usd is not None
            and cost is not None
            and cost >= budget.max_cost_usd
        ):
            return "max_cost_usd"

        return None

    def report(self) -> dict[str, Any]:
        cumulative = 0
        per_call: list[dict[str, Any]] = []

        for record in self._records:
            if record.usage is None:
                per_call.append(
                    {"call": record.call_index, "input_tokens": None,
                     "output_tokens": None, "cumulative_total": cumulative}
                )
                continue
            cumulative += record.usage.total_tokens
            per_call.append(
                {
                    "call": record.call_index,
                    "input_tokens": record.usage.input_tokens,
                    "output_tokens": record.usage.output_tokens,
                    "cumulative_total": cumulative,
                }
            )

        total = self.total
        cost = self.cost_usd()

        return {
            "calls": self.calls,
            "unreported_calls": self.unreported_calls,
            "input_tokens": total.input_tokens,
            "output_tokens": total.output_tokens,
            "total_tokens": total.total_tokens,
            "cost_usd": round(cost, 6) if cost is not None else None,
            "per_call": per_call,
        }
```

---

### `app/agent/history.py` <a id="appagenthistorypy"></a>

```python
import json
from dataclasses import asdict, dataclass
from typing import Any


@dataclass(frozen=True)
class ExecutionRecord:
    tool_name: str
    arguments: dict[str, Any]
    success: bool
    result: Any
    error: str | None
    duration_ms: float


class ExecutionHistory:
    """Stores tool executions for a single agent run."""

    def __init__(self) -> None:
        self._records: list[ExecutionRecord] = []

    def add(self, record: ExecutionRecord) -> None:
        self._records.append(record)

    def records(self) -> list[ExecutionRecord]:
        return list(self._records)

    def to_dicts(self) -> list[dict[str, Any]]:
        return [
            asdict(record)
            for record in self._records
        ]

    def to_json(self) -> str:
        return json.dumps(
            self.to_dicts(),
            indent=2,
            default=str,
        )

    def __len__(self) -> int:
        return len(self._records)
```

---

### `app/agent/ledger.py` <a id="appagentledgerpy"></a>

```python
"""Evidence ledger: objective, code-derived facts about what the agent has
actually done. Built from ExecutionHistory, never from model claims.
"""

from collections.abc import Sequence

from .history import ExecutionRecord

_MAX_PER_SECTION = 5
_MAX_ERROR_CHARS = 80
_MAX_ARG_CHARS = 40


def _clip(text: str, limit: int) -> str:
    one_line = " ".join(text.split())
    return one_line if len(one_line) <= limit else one_line[: limit - 3] + "..."


def _capped(items: list[str]) -> str:
    shown = items[:_MAX_PER_SECTION]
    extra = len(items) - len(shown)
    text = ", ".join(shown)
    return f"{text} (+{extra} more)" if extra > 0 else text


def _search_label(record: ExecutionRecord) -> str:
    query = _clip(str(record.arguments.get("query", "")), _MAX_ARG_CHARS)
    count = len(record.result) if isinstance(record.result, list) else 0
    return f'"{query}" ({count} matches)'


def _failure_label(record: ExecutionRecord) -> str:
    args = _clip(
        ", ".join(f"{v}" for v in record.arguments.values()), _MAX_ARG_CHARS
    )
    error = _clip(record.error or "unknown error", _MAX_ERROR_CHARS)
    return f"{record.tool_name}({args}): {error}"


def build_ledger(records: Sequence[ExecutionRecord]) -> str | None:
    """Return a short progress note, or None when there is nothing to report."""
    files: list[str] = []
    searches: list[str] = []
    failures: list[str] = []

    for record in records:
        if not record.success:
            failures.append(_failure_label(record))
        elif record.tool_name == "read_file":
            path = str(record.arguments.get("path", ""))
            if path and path not in files:
                files.append(path)
        elif record.tool_name == "search_text":
            searches.append(_search_label(record))

    lines: list[str] = []
    if files:
        lines.append(f"- Files read: {_capped(files)}")
    if searches:
        lines.append(f"- Searches done: {_capped(searches)}")
    if failures:
        lines.append(f"- Failed calls: {_capped(failures)}")
    if not lines:
        return None

    return (
        "System note (not from the user). Progress so far, from your actual "
        "tool calls:\n" + "\n".join(lines)
    )
```

---

### `app/agent/loop_guard.py` <a id="appagentloopguardpy"></a>

```python
import json
from collections import Counter
from typing import Any


def call_fingerprint(
    tool_name: str,
    arguments: dict[str, Any],
) -> str:
    """Stable string fingerprint; argument order does not matter."""
    canonical = json.dumps(
        arguments,
        sort_keys=True,
        ensure_ascii=False,
    )
    return f"{tool_name}:{canonical}"


class LoopGuard:
    """Blocks a tool call when the same call is made for the Nth time."""

    def __init__(self, block_on_nth_call: int = 3) -> None:
        if block_on_nth_call < 1:
            raise ValueError("block_on_nth_call must be >= 1")

        self._block_on_nth_call = block_on_nth_call
        self._counts: Counter[str] = Counter()

    def record(self, fingerprint: str) -> bool:
        """Record a call. Returns True when this call must be blocked."""
        self._counts[fingerprint] += 1
        return self._counts[fingerprint] >= self._block_on_nth_call


class ConsecutiveCounter:
    """Counts consecutive failures; any success resets it."""

    def __init__(self, limit: int) -> None:
        if limit < 1:
            raise ValueError("limit must be >= 1")

        self._limit = limit
        self._count = 0

    def failure(self) -> bool:
        self._count += 1
        return self._count >= self._limit

    def reset(self) -> None:
        self._count = 0
```

---

### `app/agent/loop.py` <a id="appagentlooppy"></a>

```python
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

_MAX_TRACE_THOUGHT_CHARS = 500
_PLAN_HEADER = "Plan (advisory; revise it if observations contradict it):"


class AgentLoop:
    """Orchestrates LLM decisions and tool execution."""

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
                state.iteration += 1
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
            return

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
```

---

### `app/agent/nudges.py` <a id="appagentnudgespy"></a>

```python
"""Code-triggered corrective nudges. Pure functions over ExecutionRecord:
no provider or loop knowledge. A nudge is advisory text appended as an
append-only user message (same mechanism as the evidence ledger).
"""

from collections.abc import Sequence

from .history import ExecutionRecord

_MAX_ERROR_CHARS = 100
_MAX_LISTED = 2


def _clip(text: str, limit: int) -> str:
    one_line = " ".join(text.split())
    return one_line if len(one_line) <= limit else one_line[: limit - 3] + "..."


def trailing_failures(records: Sequence[ExecutionRecord]) -> list[ExecutionRecord]:
    """Consecutive failed calls at the END of history (a success resets)."""
    tail: list[ExecutionRecord] = []
    for record in reversed(records):
        if record.success:
            break
        tail.append(record)
    tail.reverse()
    return tail


def failure_nudge(
    records: Sequence[ExecutionRecord], *, threshold: int = 2
) -> str | None:
    """Return a recovery note when the last `threshold`+ calls all failed."""
    tail = trailing_failures(records)
    if len(tail) < threshold:
        return None
    shown = tail[-_MAX_LISTED:]
    details = "; ".join(
        f"{r.tool_name}: {_clip(r.error or 'unknown error', _MAX_ERROR_CHARS)}"
        for r in shown
    )
    return (
        "System note (not from the user). Your last "
        f"{len(tail)} tool calls failed ({details}). "
        "Check paths with list_files before retrying the same call."
    )


EMPTY_ANSWER_NUDGE = (
    "System note (not from the user). Your last reply contained neither a "
    "tool call nor a final answer. Call a tool, or give your final answer."
)


def trailing_empty_searches(records: Sequence[ExecutionRecord]) -> list[str]:
    """Queries of consecutive empty successful searches at the END of history."""
    queries: list[str] = []
    for record in reversed(records):
        if record.tool_name == "read_file" and record.success:
            break
        if record.tool_name != "search_text" or not record.success:
            continue
        if isinstance(record.result, list) and len(record.result) == 0:
            queries.append(str(record.arguments.get("query", "")))
        else:
            break
    queries.reverse()
    return queries


def no_progress_nudge(
    records: Sequence[ExecutionRecord], *, threshold: int = 3
) -> str | None:
    queries = trailing_empty_searches(records)
    if len(queries) < threshold:
        return None
    shown = ", ".join(f'"{_clip(q, 30)}"' for q in queries[-threshold:])
    return (
        "System note (not from the user). Your last "
        f"{len(queries)} searches returned no matches ({shown}). "
        "If the repository does not contain what the task asks about, "
        "say so clearly in your final answer instead of searching further."
    )
```

---

### `app/agent/plan.py` <a id="appagentplanpy"></a>

```python
from dataclasses import dataclass, field
from enum import Enum


class StepStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    DONE = "done"
    FAILED = "failed"


@dataclass
class PlanStep:
    id: int
    description: str
    status: StepStatus = StepStatus.PENDING


@dataclass
class Plan:
    steps: list[PlanStep] = field(default_factory=list)

    @classmethod
    def from_descriptions(cls, descriptions: list[str], *, max_steps: int = 8) -> "Plan":
        cleaned = [d.strip() for d in descriptions if d and d.strip()]
        return cls(
            steps=[
                PlanStep(id=i, description=d)
                for i, d in enumerate(cleaned[:max_steps], start=1)
            ]
        )

    def __len__(self) -> int:
        return len(self.steps)

    def render(self) -> str:
        return "\n".join(f"{s.id}. {s.description}" for s in self.steps)
```

---

### `app/agent/plan_parsing.py` <a id="appagentplanparsingpy"></a>

```python
import re

_STEP = re.compile(r"^\s*(?:\d+[.)]|[-*])\s+(.+?)\s*$")


def parse_numbered_steps(text: str) -> list[str]:
    steps: list[str] = []
    for line in text.splitlines():
        match = _STEP.match(line)
        if match:
            steps.append(match.group(1))
    return steps
```

---

### `app/agent/planner.py` <a id="appagentplannerpy"></a>

```python
from collections.abc import Callable
from dataclasses import dataclass

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from app.llm import LLMClient, LLMResponse
from app.llm.types import user_message
from app.tools.schema_utils import strict_json_schema

from .plan import Plan
from .prompts import PLANNER_V1


class PlanSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    steps: list[str] = Field(
        description="Ordered steps; each is one short sentence."
    )


@dataclass(frozen=True)
class PlanOutcome:
    response: LLMResponse
    plan: Plan | None
    failure: str | None = None


class Planner:
    def __init__(self, client: LLMClient, *, max_steps: int = 6) -> None:
        self._client = client
        self._max_steps = max_steps
        self._schema = strict_json_schema(PlanSpec)

    def make(
        self, task: str, should_abort: Callable[[], bool] | None = None
    ) -> PlanOutcome:
        response = self._client.complete(
            messages=[user_message(f"{PLANNER_V1.text}\n\nTask: {task}")],
            tools=[],
            should_abort=should_abort,
            output_schema=self._schema,
        )
        try:
            spec = PlanSpec.model_validate_json(response.text)
        except ValidationError as exc:
            return PlanOutcome(
                response, None, f"invalid plan JSON: {exc.error_count()} error(s)"
            )

        plan = Plan.from_descriptions(spec.steps, max_steps=self._max_steps)
        if len(plan) == 0:
            return PlanOutcome(response, None, "plan has no steps")
        return PlanOutcome(response, plan)
```

---

### `app/agent/prompts.py` <a id="appagentpromptspy"></a>

```python
import hashlib
from dataclasses import dataclass


@dataclass(frozen=True)
class Prompt:
    name: str
    text: str

    @property
    def sha(self) -> str:
        return hashlib.sha256(self.text.encode("utf-8")).hexdigest()[:8]

    @property
    def label(self) -> str:
        return f"{self.name}@{self.sha}"


_BASE = (
    "You are a software engineering agent. "
    "You must ONLY call the tools explicitly provided: list_files, read_file, search_text. "
    "Never use any namespace prefixes or tools not defined. "
    "Only use workspace-relative paths. "
    "Do not invent file contents. If something does not exist, say so."
)

_GROUNDING = (
    " Never state facts about the repository from general knowledge. "
    "Every claim in your answer must come from a tool result you obtained "
    "in this run. If you have not read the relevant file yet, read it "
    "before answering."
)

BASELINE = Prompt("baseline", _BASE)
GROUNDED_V1 = Prompt("grounded-v1", _BASE + _GROUNDING)

PLANNER_V1 = Prompt(
    "planner-v1",
    "Write a short plan for answering the task below. The agent that will "
    "execute it can only use these tools, all on the repository: list_files, "
    "read_file, search_text. Write at most 6 steps, each one short sentence "
    "saying what to look for or read. Do not answer the task itself.",
)

PROMPTS: dict[str, Prompt] = {p.name: p for p in (BASELINE, GROUNDED_V1)}


def get_prompt(name: str) -> Prompt:
    try:
        return PROMPTS[name]
    except KeyError:
        raise KeyError(
            f"unknown prompt '{name}'; available: {sorted(PROMPTS)}"
        ) from None
```

---

### `app/agent/state.py` <a id="appagentstatepy"></a>

```python
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from app.llm import AttemptRecord

from .cost import UsageTracker
from .history import ExecutionHistory
from .plan import Plan


class AgentStatus(str, Enum):
    RUNNING = "running"
    COMPLETED = "completed"
    MAX_ITERATIONS = "max_iterations"
    TIMEOUT = "timeout"
    LOOP_DETECTED = "loop_detected"
    TOKEN_BUDGET_EXCEEDED = "token_budget_exceeded"
    LLM_FAILED = "llm_failed"


@dataclass(frozen=True)
class Thought:
    iteration: int
    text: str


@dataclass
class AgentState:
    conversation: list[dict[str, Any]] = field(default_factory=list)
    iteration: int = 0
    status: AgentStatus = AgentStatus.RUNNING
    final_response: str | None = None
    error: str | None = None
    history: ExecutionHistory = field(default_factory=ExecutionHistory)
    usage: UsageTracker = field(default_factory=UsageTracker)
    llm_attempts: list[AttemptRecord] = field(default_factory=list)
    run_id: str | None = None
    thoughts: list[Thought] = field(default_factory=list)
    plan: Plan | None = None
    empty_answer_retries: int = 0
    last_nudged_failures: int = 0
    last_nudged_empty: int = 0

    @property
    def is_finished(self) -> bool:
        return self.status != AgentStatus.RUNNING
```

---

### `app/agent/trace.py` <a id="appagenttracepy"></a>

```python
import json
import sys
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Protocol, TextIO


@dataclass(frozen=True)
class TraceEvent:
    run_id: str
    seq: int
    ts: str
    type: str
    data: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "seq": self.seq,
            "ts": self.ts,
            "type": self.type,
            **self.data,
        }


class TraceSink(Protocol):
    def write(self, event: TraceEvent) -> None: ...


class InMemorySink:
    def __init__(self) -> None:
        self.events: list[TraceEvent] = []

    def write(self, event: TraceEvent) -> None:
        self.events.append(event)

    def types(self) -> list[str]:
        return [e.type for e in self.events]


class JsonlFileSink:
    def __init__(self, path: str | Path) -> None:
        self._path = Path(path)
        self._path.parent.mkdir(parents=True, exist_ok=True)

    def write(self, event: TraceEvent) -> None:
        line = json.dumps(event.to_dict(), ensure_ascii=False, default=str)
        with self._path.open("a", encoding="utf-8") as handle:
            handle.write(line + "\n")


def _utc_now_iso() -> str:
    return datetime.now(UTC).isoformat()


class TraceRecorder:
    def __init__(
        self,
        sink: TraceSink,
        *,
        run_id: str | None = None,
        now: Callable[[], str] = _utc_now_iso,
        err: TextIO | None = None,
    ) -> None:
        self._sink = sink
        self.run_id = run_id or uuid.uuid4().hex
        self._now = now
        self._seq = 0
        self._err = err or sys.stderr

    def emit(self, type_: str, **data: Any) -> None:
        self._seq += 1
        event = TraceEvent(
            run_id=self.run_id,
            seq=self._seq,
            ts=self._now(),
            type=type_,
            data=data,
        )
        try:
            self._sink.write(event)
        except Exception as exc:
            print(f"trace sink failed: {exc!r}", file=self._err)
```
