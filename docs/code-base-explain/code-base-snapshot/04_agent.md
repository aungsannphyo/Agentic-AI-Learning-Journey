# Agent Runtime — Agent Runtime & Control Layer Snapshot (`app/agent/`)

AgentLoop orchestration (refactored cognitive complexity 6), LoopGuard, ConsecutiveCounter, wall-clock & token budgets, state models, and structured tracing engine.

**Files count**: 9 files | **Active status**: 151 tests passed, ruff/mypy clean

## ဖိုင်များ မာတိကာ (Table of Contents)

- [`app/agent/__init__.py`](#appagentinitpy)
- [`app/agent/budget.py`](#appagentbudgetpy)
- [`app/agent/clock.py`](#appagentclockpy)
- [`app/agent/cost.py`](#appagentcostpy)
- [`app/agent/history.py`](#appagenthistorypy)
- [`app/agent/loop_guard.py`](#appagentloopguardpy)
- [`app/agent/loop.py`](#appagentlooppy)
- [`app/agent/state.py`](#appagentstatepy)
- [`app/agent/trace.py`](#appagenttracepy)

---

### `app/agent/__init__.py` <a id="appagentinitpy"></a>

```python
from .budget import BudgetTracker, RuntimeBudget
from .clock import Clock, MonotonicClock
from .cost import ModelPricing, TokenBudget, UsageTracker
from .history import ExecutionHistory, ExecutionRecord
from .loop import AgentLoop
from .loop_guard import ConsecutiveCounter, LoopGuard, call_fingerprint
from .state import AgentState, AgentStatus
from .trace import InMemorySink, JsonlFileSink, TraceEvent, TraceRecorder, TraceSink

__all__ = [
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
    "RuntimeBudget",
    "TokenBudget",
    "TraceEvent",
    "TraceRecorder",
    "TraceSink",
    "UsageTracker",
    "call_fingerprint",
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
    """Blocks a tool call when the same call is made for the Nth time.

    block_on_nth_call=3 means the 1st and 2nd identical calls are allowed
    and the 3rd is blocked BEFORE execution.
    """

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
    """Counts consecutive failures; any success resets it.

    failure() returns True when the Nth consecutive failure is reached.
    """

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
from .loop_guard import ConsecutiveCounter, LoopGuard, call_fingerprint
from .state import AgentState, AgentStatus
from .trace import TraceRecorder, TraceSink


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
        self._max_consecutive_malformed = max_consecutive_malformed
        self._trace_sink = trace

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

        if not response.tool_calls:
            self._handle_final_response(response, state)
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
        self, response: LLMResponse, state: AgentState
    ) -> None:
        if not response.text.strip():
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


class AgentStatus(str, Enum):
    RUNNING = "running"
    COMPLETED = "completed"
    MAX_ITERATIONS = "max_iterations"
    TIMEOUT = "timeout"
    LOOP_DETECTED = "loop_detected"
    TOKEN_BUDGET_EXCEEDED = "token_budget_exceeded"
    LLM_FAILED = "llm_failed"


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
    """One immutable, JSON-serializable trace record."""

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
    """Collects events in a list. For tests and ad-hoc inspection."""

    def __init__(self) -> None:
        self.events: list[TraceEvent] = []

    def write(self, event: TraceEvent) -> None:
        self.events.append(event)

    def types(self) -> list[str]:
        return [e.type for e in self.events]


class JsonlFileSink:
    """Appends one JSON object per line; flushes every event so a crash
    keeps everything written so far."""

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
    """Per-run emitter. Owns run_id and the sequence counter.

    A sink failure must never break the run: observability is not
    business logic. Failures go to stderr once per event.
    """

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

---
