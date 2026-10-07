# Agent Runtime — Codebase Source Snapshot

ဤဖိုင်သည် **Agent Runtime** codebase တစ်ခုလုံးရှိ active source code ဖိုင်များအားလုံးကို LLM / Agent Context အဖြစ် အလွယ်တကူ ထည့်သွင်းအသုံးပြုနိုင်ရန် စုစည်းထားသော Single Source Snapshot ဖြစ်ပါသည်။

**Active Status**: Week 3 / Day 2 Complete (151 tests passing, ruff & mypy clean, 36 source files)

## စုစည်းထားသော ဖိုင်များ မာတိကာ

- [`app/main.py`](#appmainpy)
- [`app/trace_view.py`](#apptraceviewpy)
- [`conftest.py`](#conftestpy)
- [`app/llm/types.py`](#appllmtypespy)
- [`app/llm/errors.py`](#appllmerrorspy)
- [`app/llm/retry.py`](#appllmretrypy)
- [`app/llm/llm_errors.py`](#appllmllmerrorspy)
- [`app/llm/client.py`](#appllmclientpy)
- [`app/llm/openai_client.py`](#appllmopenaiclientpy)
- [`app/llm/fake_client.py`](#appllmfakeclientpy)
- [`app/llm/resilient_client.py`](#appllmresilientclientpy)
- [`app/llm/openai_tools.py`](#appllmopenaitoolspy)
- [`app/llm/__init__.py`](#appllminitpy)
- [`app/tools/base.py`](#apptoolsbasepy)
- [`app/tools/call.py`](#apptoolscallpy)
- [`app/tools/call_parsing.py`](#apptoolscallparsingpy)
- [`app/tools/execution.py`](#apptoolsexecutionpy)
- [`app/tools/workspace.py`](#apptoolsworkspacepy)
- [`app/tools/schemas.py`](#apptoolsschemaspy)
- [`app/tools/schema_utils.py`](#apptoolsschemautilspy)
- [`app/tools/validation.py`](#apptoolsvalidationpy)
- [`app/tools/registry.py`](#apptoolsregistrypy)
- [`app/tools/executor.py`](#apptoolsexecutorpy)
- [`app/tools/list_files.py`](#apptoolslistfilespy)
- [`app/tools/read_file.py`](#apptoolsreadfilepy)
- [`app/tools/search_text.py`](#apptoolssearchtextpy)
- [`app/tools/__init__.py`](#apptoolsinitpy)
- [`app/agent/clock.py`](#appagentclockpy)
- [`app/agent/budget.py`](#appagentbudgetpy)
- [`app/agent/cost.py`](#appagentcostpy)
- [`app/agent/history.py`](#appagenthistorypy)
- [`app/agent/loop_guard.py`](#appagentloopguardpy)
- [`app/agent/state.py`](#appagentstatepy)
- [`app/agent/trace.py`](#appagenttracepy)
- [`app/agent/loop.py`](#appagentlooppy)
- [`app/agent/__init__.py`](#appagentinitpy)
- [`tests/builders.py`](#testsbuilderspy)

---

### `app/main.py` <a id="appmainpy"></a>

```python
import json
import os
from pathlib import Path

from dotenv import load_dotenv

from app.agent import (
    AgentLoop,
    JsonlFileSink,
    LoopGuard,
    ModelPricing,
    RuntimeBudget,
    TokenBudget,
)
from app.llm import OpenAIClient, ResilientClient, RetryPolicy
from app.tools import (
    ListFilesTool,
    ReadFileTool,
    SearchTextTool,
    ToolExecutor,
    ToolRegistry,
    Workspace,
)


def build_registry(workspace: Workspace) -> ToolRegistry:
    registry = ToolRegistry()
    registry.register(ListFilesTool(workspace))
    registry.register(ReadFileTool(workspace))
    registry.register(SearchTextTool(workspace))
    return registry


def pricing_from_env() -> ModelPricing | None:
    raw_in = os.getenv("MODEL_INPUT_USD_PER_MTOK")
    raw_out = os.getenv("MODEL_OUTPUT_USD_PER_MTOK")
    if not raw_in or not raw_out:
        return None
    return ModelPricing(float(raw_in), float(raw_out))


def main() -> None:
    load_dotenv()

    workspace = Workspace(Path.cwd())
    registry = build_registry(workspace)
    executor = ToolExecutor(registry)

    runtime_budget = RuntimeBudget(
        max_wall_time_seconds=120.0,
        per_call_timeout_seconds=30.0,
    )

    inner = OpenAIClient(
        system_prompt=(
            "You are a software engineering agent. "
            "You must ONLY call the tools explicitly provided: list_files, read_file, search_text. "
            "Never use any namespace prefixes or tools not defined (such as repo_browser). "
            "Only use workspace-relative paths. "
            "Do not invent file contents."
        ),
        timeout_seconds=runtime_budget.per_call_timeout_seconds,
    )

    client = ResilientClient(
        inner,
        RetryPolicy(
            max_attempts=5,
            base_delay_seconds=3.0,
            max_delay_seconds=25.0,
        ),
    )

    agent = AgentLoop(
        client=client,
        registry=registry,
        executor=executor,
        max_iterations=10,
        runtime_budget=runtime_budget,
        loop_guard_factory=lambda: LoopGuard(block_on_nth_call=3),
        token_budget=TokenBudget(
            max_total_tokens=int(os.getenv("AGENT_MAX_TOTAL_TOKENS", "50000"))
        ),
        pricing=pricing_from_env(),
        trace=JsonlFileSink(Path("traces") / "runs.jsonl"),
    )

    state = agent.run(
        "Explain the app directory and identify the main agent loop file."
    )

    print(f"\n=== Run ID: {state.run_id} (traces/runs.jsonl) ===")

    print("\n=== Final Response ===\n")
    print(state.final_response)

    print(f"\n=== Status: {state.status.value} ===")
    if state.error:
        print(state.error)

    if state.llm_attempts:
        print("\n=== LLM Retry Log ===\n")
        for rec in state.llm_attempts:
            print(rec)

    print("\n=== Usage Report ===\n")
    print(json.dumps(state.usage.report(), indent=2))

    print("\n=== Execution History ===\n")
    print(state.history.to_json())


if __name__ == "__main__":
    main()
```

---

### `app/trace_view.py` <a id="apptraceviewpy"></a>

```python
"""Read-only viewer for traces/runs.jsonl.

Works on plain dicts (the JSONL schema), not on runtime types, so it stays
decoupled from the agent loop. Older traces without attempt_log still render.
"""

import argparse
import json
import sys
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

DEFAULT_FILE = Path("traces") / "runs.jsonl"
Event = dict[str, Any]


@dataclass
class ToolRow:
    name: str
    ok: bool
    ms: float
    error: str | None


@dataclass
class IterationRow:
    iteration: int
    llm_ms: float = 0.0
    input_tokens: int | None = None
    output_tokens: int | None = None
    retries: int = 0
    failed: bool = False
    tools: list[ToolRow] = field(default_factory=list)


@dataclass
class RunSummary:
    run_id: str
    prompt: str
    status: str
    error: str | None
    finished: bool
    rows: list[IterationRow]
    guards: list[str]
    wall_ms: float | None
    llm_ms: float
    tool_ms: float
    retries: int
    total_tokens: int | None
    cost_usd: float | None


def load_events(path: Path) -> list[Event]:
    events: list[Event] = []
    with path.open(encoding="utf-8") as handle:
        for number, line in enumerate(handle, start=1):
            line = line.strip()
            if not line:
                continue
            try:
                events.append(json.loads(line))
            except json.JSONDecodeError:
                print(f"warning: skipping malformed line {number}", file=sys.stderr)
    return events


def run_ids(events: Sequence[Event]) -> list[str]:
    seen: list[str] = []
    for event in events:
        rid = event.get("run_id")
        if isinstance(rid, str) and rid not in seen:
            seen.append(rid)
    return seen


def select_run(events: Sequence[Event], run_id: str) -> list[Event]:
    ids = run_ids(events)
    if not ids:
        raise LookupError("trace file has no runs")
    if run_id == "latest":
        chosen = ids[-1]
    else:
        matches = [i for i in ids if i.startswith(run_id)]
        if not matches:
            raise LookupError(f"no run matches '{run_id}'")
        if len(matches) > 1:
            raise LookupError(
                f"'{run_id}' is ambiguous ({len(matches)} runs); use more characters"
            )
        chosen = matches[0]
    return sorted(
        (e for e in events if e.get("run_id") == chosen),
        key=lambda e: e.get("seq", 0),
    )


def _retries(event: Event) -> int:
    log = event.get("attempt_log")
    if log is not None:
        return len(log)
    # older traces: `attempts` was a total count on success
    return max(int(event.get("attempts", 1)) - 1, 0)


def _wall_ms(events: Sequence[Event]) -> float | None:
    try:
        first = datetime.fromisoformat(events[0]["ts"])
        last = datetime.fromisoformat(events[-1]["ts"])
    except (KeyError, ValueError, IndexError):
        return None
    return (last - first).total_seconds() * 1000


def summarize(events: Sequence[Event]) -> RunSummary:
    if not events:
        raise LookupError("no events")

    by_iteration: dict[int, IterationRow] = {}
    rows: list[IterationRow] = []
    guards: list[str] = []
    prompt = ""
    finished: Event | None = None

    def row_for(iteration: int) -> IterationRow:
        row = by_iteration.get(iteration)
        if row is None:
            row = IterationRow(iteration=iteration)
            by_iteration[iteration] = row
            rows.append(row)
        return row

    for event in events:
        kind = event.get("type")
        if kind == "run_started":
            prompt = str(event.get("prompt", ""))
        elif kind == "llm_call":
            row = row_for(int(event.get("iteration", 0)))
            row.llm_ms = float(event.get("latency_ms", 0.0))
            row.input_tokens = event.get("input_tokens")
            row.output_tokens = event.get("output_tokens")
            row.retries = _retries(event)
            row.failed = bool(event.get("failed", False))
        elif kind == "tool_call":
            row_for(int(event.get("iteration", 0))).tools.append(
                ToolRow(
                    name=str(event.get("tool_name")),
                    ok=bool(event.get("success")),
                    ms=float(event.get("duration_ms", 0.0)),
                    error=event.get("error"),
                )
            )
        elif kind == "guard_triggered":
            guards.append(f"{event.get('guard')}: {event.get('detail')}")
        elif kind == "run_finished":
            finished = event

    return RunSummary(
        run_id=str(events[0].get("run_id")),
        prompt=prompt,
        status=str(finished["status"]) if finished else "incomplete (no run_finished)",
        error=finished.get("error") if finished else None,
        finished=finished is not None,
        rows=rows,
        guards=guards,
        wall_ms=_wall_ms(events),
        llm_ms=sum(r.llm_ms for r in rows),
        tool_ms=sum(t.ms for r in rows for t in r.tools),
        retries=sum(r.retries for r in rows),
        total_tokens=finished.get("total_tokens") if finished else None,
        cost_usd=finished.get("cost_usd") if finished else None,
    )


def _num(value: float | None, spec: str = "") -> str:
    return "-" if value is None else format(value, spec)


def render(summary: RunSummary) -> str:
    prompt = summary.prompt.replace("\n", " ")
    if len(prompt) > 80:
        prompt = prompt[:77] + "..."

    lines = [
        f"run {summary.run_id}  status={summary.status}  iterations={len(summary.rows)}",
        f"prompt: {prompt}",
        "",
        f"{'iter':>4} {'llm_ms':>9} {'in_tok':>7} {'out_tok':>8} {'retries':>8}  tools",
    ]
    for row in summary.rows:
        tools = ", ".join(
            f"{t.name}{'' if t.ok else ' FAIL'} {t.ms:.1f}ms" for t in row.tools
        )
        flag = " (LLM FAILED)" if row.failed else ""
        lines.append(
            f"{row.iteration:>4} {row.llm_ms:>9.1f} "
            f"{_num(row.input_tokens):>7} {_num(row.output_tokens):>8} "
            f"{row.retries:>8}  {tools}{flag}"
        )

    lines.append("")
    if summary.wall_ms is not None:
        share = (summary.llm_ms / summary.wall_ms * 100) if summary.wall_ms else 0.0
        lines.append(
            f"wall={summary.wall_ms / 1000:.2f}s  llm={summary.llm_ms / 1000:.2f}s "
            f"({share:.0f}%)  tools={summary.tool_ms / 1000:.3f}s  "
            f"retries={summary.retries}"
        )
    lines.append(
        f"tokens={_num(summary.total_tokens)}  cost_usd={_num(summary.cost_usd)}"
    )

    if summary.rows:
        slowest = max(summary.rows, key=lambda r: r.llm_ms)
        lines.append(
            f"slowest LLM call: iter {slowest.iteration} "
            f"({slowest.llm_ms:.0f}ms, retries={slowest.retries})"
        )
    for guard in summary.guards:
        lines.append(f"guard: {guard}")
    if summary.error:
        lines.append(f"error: {summary.error}")
    if not summary.finished:
        lines.append("note: trace has no run_finished (crash or still running)")
    return "\n".join(lines)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="trace_view")
    parser.add_argument("run_id", nargs="?", default="latest",
                        help="run id, unique prefix, or 'latest'")
    parser.add_argument("--file", type=Path, default=DEFAULT_FILE)
    parser.add_argument("--list", action="store_true", help="list run ids")
    args = parser.parse_args(argv)

    try:
        events = load_events(args.file)
        if args.list:
            for rid in run_ids(events):
                print(rid)
            return 0
        print(render(summarize(select_run(events, args.run_id))))
        return 0
    except (OSError, LookupError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
```

---

### `conftest.py` <a id="conftestpy"></a>

```python
# conftest.py — project-root conftest
# Placing this file here tells pytest to add the agent-runtime/ directory
# to sys.path so that `from app.xxx import ...` works in all test modules.
```

---

### `app/llm/types.py` <a id="appllmtypespy"></a>

```python
from dataclasses import dataclass, field
from typing import Any

from app.tools import ToolCall

from .retry import ErrorKind


@dataclass(frozen=True)
class Usage:
    """Provider-independent token usage for one LLM call."""

    input_tokens: int = 0
    output_tokens: int = 0

    @property
    def total_tokens(self) -> int:
        return self.input_tokens + self.output_tokens

    def __add__(self, other: "Usage") -> "Usage":
        return Usage(
            input_tokens=self.input_tokens + other.input_tokens,
            output_tokens=self.output_tokens + other.output_tokens,
        )


def _first_int(obj: Any, *names: str) -> int | None:
    for name in names:
        value = getattr(obj, name, None)
        if isinstance(value, int) and not isinstance(value, bool):
            return value
    return None


def extract_usage(response: Any) -> Usage | None:
    """
    Normalise provider usage into Usage.

    Returns None (NOT zero) when the provider did not report usage.
    Silent zero would make budget enforcement fail open.

    Supports Responses-API naming (input_tokens/output_tokens) and
    Chat-Completions naming (prompt_tokens/completion_tokens).
    """
    raw = getattr(response, "usage", None)
    if raw is None:
        return None

    input_tokens = _first_int(raw, "input_tokens", "prompt_tokens")
    output_tokens = _first_int(raw, "output_tokens", "completion_tokens")

    if input_tokens is None or output_tokens is None:
        return None

    return Usage(input_tokens=input_tokens, output_tokens=output_tokens)


@dataclass(frozen=True)
class AttemptRecord:
    attempt: int
    error: str
    kind: ErrorKind
    delay_seconds: float
    retry_after_seconds: float | None = None
    latency_ms: float = 0.0


@dataclass(frozen=True)
class LLMResponse:
    """Provider-independent result of one LLM call.

    assistant_items are opaque, JSON-serializable provider items
    (message / function_call / reasoning ...) that the same provider
    must be given back on the next call. The loop stores them but
    never inspects them.
    """

    text: str
    tool_calls: tuple[ToolCall, ...]
    usage: Usage | None
    assistant_items: tuple[dict[str, Any], ...] = field(default_factory=tuple)
    attempts: tuple[AttemptRecord, ...] = field(default_factory=tuple)


# --- provider-neutral conversation messages -------------------------------
# Each message is a plain JSON-serializable dict with a "kind" key:
#   {"kind": "user", "text": str}
#   {"kind": "assistant", "items": [dict, ...]}      (opaque provider items)
#   {"kind": "tool_result", "call_id": str, "output": str}


def user_message(text: str) -> dict[str, Any]:
    return {"kind": "user", "text": text}


def assistant_message(response: LLMResponse) -> dict[str, Any]:
    return {"kind": "assistant", "items": list(response.assistant_items)}


def tool_result_message(call_id: str, output: str) -> dict[str, Any]:
    return {"kind": "tool_result", "call_id": call_id, "output": output}
```

---

### `app/llm/errors.py` <a id="appllmerrorspy"></a>

```python
from .retry import ErrorKind
from .types import AttemptRecord


class LLMCallFailed(Exception):
    """Raised when an LLM call fails permanently or exhausts retries."""

    def __init__(
        self,
        message: str,
        *,
        attempts: int,
        kind: ErrorKind,
        attempt_log: tuple[AttemptRecord, ...] = (),
    ) -> None:
        super().__init__(message)
        self.attempts = attempts
        self.kind = kind
        self.attempt_log = attempt_log


class DeadlineExceeded(Exception):
    """Raised when the run deadline expires while waiting to retry."""

    def __init__(
        self, message: str, *, attempt_log: tuple[AttemptRecord, ...] = ()
    ) -> None:
        super().__init__(message)
        self.attempt_log = attempt_log
```

---

### `app/llm/retry.py` <a id="appllmretrypy"></a>

```python
from dataclasses import dataclass
from enum import Enum


class ErrorKind(str, Enum):
    TRANSIENT = "transient"
    PERMANENT = "permanent"


@dataclass(frozen=True)
class RetryDecision:
    should_retry: bool
    delay_seconds: float
    reason: str


@dataclass(frozen=True)
class RetryPolicy:
    max_attempts: int = 3
    base_delay_seconds: float = 0.5
    max_delay_seconds: float = 8.0

    def __post_init__(self) -> None:
        if self.max_attempts < 1:
            raise ValueError("max_attempts must be >= 1")

        if self.base_delay_seconds < 0:
            raise ValueError(
                "base_delay_seconds must be >= 0"
            )

        if self.max_delay_seconds < 0:
            raise ValueError(
                "max_delay_seconds must be >= 0"
            )

    def classify(self, error_kind: ErrorKind) -> bool:
        return error_kind == ErrorKind.TRANSIENT

    def decide(
        self,
        *,
        attempt: int,
        error_kind: ErrorKind,
    ) -> RetryDecision:
        if attempt < 1:
            raise ValueError("attempt must be >= 1")

        if not self.classify(error_kind):
            return RetryDecision(
                should_retry=False,
                delay_seconds=0.0,
                reason="permanent error",
            )

        if attempt >= self.max_attempts:
            return RetryDecision(
                should_retry=False,
                delay_seconds=0.0,
                reason="retry budget exhausted",
            )

        delay = min(
            self.base_delay_seconds * (2 ** (attempt - 1)),
            self.max_delay_seconds,
        )

        return RetryDecision(
            should_retry=True,
            delay_seconds=delay,
            reason="transient error",
        )
```

---

### `app/llm/llm_errors.py` <a id="appllmllmerrorspy"></a>

```python
import re

import openai

from .retry import ErrorKind

_TRANSIENT: tuple[type[Exception], ...] = (
    openai.RateLimitError,
    openai.APITimeoutError,
    openai.APIConnectionError,
    openai.InternalServerError,
)

_HINT = re.compile(
    r"try again in\s+(\d+(?:\.\d+)?(?:ms|s|m)(?:\s*\d+(?:\.\d+)?(?:ms|s|m))*)",
    re.IGNORECASE,
)
_PART = re.compile(r"(\d+(?:\.\d+)?)(ms|s|m)")
_UNIT_SECONDS = {"ms": 0.001, "s": 1.0, "m": 60.0}


def classify_llm_error(error: Exception) -> ErrorKind:
    """
    Map an LLM-call exception to a retry classification.

    Unknown errors are PERMANENT: retrying something we do not
    understand is worse than failing loudly.

    NOTE: APITimeoutError subclasses APIConnectionError in the SDK;
    both are listed explicitly so intent survives a refactor.
    """
    if isinstance(error, _TRANSIENT):
        return ErrorKind.TRANSIENT
    return ErrorKind.PERMANENT


def _from_header(error: Exception) -> float | None:
    headers = getattr(getattr(error, "response", None), "headers", None)
    if headers is None:
        return None
    raw = headers.get("retry-after")
    if raw is None:
        return None
    try:
        value = float(raw)
    except (TypeError, ValueError):
        return None  # HTTP-date form is not supported
    return value if value >= 0 else None


def _from_message(error: Exception) -> float | None:
    match = _HINT.search(str(error))
    if match is None:
        return None
    parts = _PART.findall(match.group(1))
    if not parts:
        return None
    return sum(float(num) * _UNIT_SECONDS[unit] for num, unit in parts)


def retry_after_seconds(error: Exception) -> float | None:
    """Provider's own suggestion for how long to wait, if it gave one.

    Header first, then the "try again in 1m30.5s" phrase in the message.
    Returns None when neither is present or parseable.
    """
    header = _from_header(error)
    if header is not None:
        return header
    return _from_message(error)
```

---

### `app/llm/client.py` <a id="appllmclientpy"></a>

```python
from collections.abc import Callable, Sequence
from typing import Any, Protocol

from app.tools import Tool

from .types import LLMResponse


class LLMClient(Protocol):
    """Provider-independent contract used by the agent loop.

    messages are provider-neutral (see app.llm.types message helpers).
    should_abort is consulted only by retry layers; plain provider
    clients accept and ignore it.
    """

    def complete(
        self,
        *,
        messages: list[dict[str, Any]],
        tools: Sequence[Tool],
        should_abort: Callable[[], bool] | None = None,
    ) -> LLMResponse:
        ...
```

---

### `app/llm/openai_client.py` <a id="appllmopenaiclientpy"></a>

```python
import os
from collections.abc import Callable, Sequence
from typing import Any

from openai import OpenAI

from app.tools import Tool, parse_tool_call

from .openai_tools import to_openai_tool
from .types import LLMResponse, extract_usage


def _function_calls(output: Sequence[Any]) -> list[Any]:
    """Provider output is untrusted; select by structural `type` tag.

    Typed as Any on purpose: the SDK union is wide and tests use
    duck-typed fakes, so narrowing by isinstance would couple both.
    """
    return [i for i in output if getattr(i, "type", None) == "function_call"]


class OpenAIClient:
    """OpenAI Responses API implementation of LLMClient (Groq-compatible)."""

    def __init__(
        self,
        *,
        model: str | None = None,
        temperature: float | None = None,
        system_prompt: str | None = None,
        timeout_seconds: float | None = None,
        sdk_client: Any | None = None,
    ) -> None:
        self._client: Any = sdk_client or OpenAI(
            api_key=os.environ["OPENAI_API_KEY"],
            base_url="https://api.groq.com/openai/v1",
            timeout=timeout_seconds,
            max_retries=0,
        )
        self._model: str = (model or os.getenv(
            "OPENAI_MODEL")) or "openai/gpt-oss-120b"
        self._temperature = (
            temperature
            if temperature is not None
            else float(os.getenv("OPENAI_TEMPERATURE", "0.2"))
        )
        self._system_prompt: str | None = system_prompt

    @staticmethod
    def _to_openai_input(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
        items: list[dict[str, Any]] = []
        for message in messages:
            kind = message["kind"]
            if kind == "user":
                items.append({"role": "user", "content": message["text"]})
            elif kind == "assistant":
                items.extend(message["items"])
            elif kind == "tool_result":
                items.append(
                    {
                        "type": "function_call_output",
                        "call_id": message["call_id"],
                        "output": message["output"],
                    }
                )
            else:
                raise ValueError(f"unknown message kind: {kind}")
        return items

    @staticmethod
    def _dump_item(item: Any) -> dict[str, Any]:
        if isinstance(item, dict):
            return item
        dump = getattr(item, "model_dump", None)
        if callable(dump):
            return dump(mode="json", exclude_none=True)
        raise TypeError(
            f"cannot serialize provider item of type {type(item).__name__}"
        )

    def complete(
        self,
        *,
        messages: list[dict[str, Any]],
        tools: Sequence[Tool],
        should_abort: Callable[[], bool] | None = None,
    ) -> LLMResponse:
        del should_abort
        response = self._client.responses.create(
            model=self._model,
            instructions=self._system_prompt,
            input=self._to_openai_input(messages),
            tools=[to_openai_tool(tool) for tool in tools],
            temperature=self._temperature,
        )

        tool_calls = tuple(
            parse_tool_call(
                call_id=item.call_id,
                name=item.name,
                raw_arguments=item.arguments,
            )
            for item in _function_calls(response.output)
        )

        return LLMResponse(
            text=response.output_text,
            tool_calls=tool_calls,
            usage=extract_usage(response),
            assistant_items=tuple(self._dump_item(i) for i in response.output),
        )
```

---

### `app/llm/fake_client.py` <a id="appllmfakeclientpy"></a>

```python
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from typing import Any

from app.tools import parse_tool_call

from .types import LLMResponse, extract_usage


@dataclass
class FakeResponse:
    output_text: str
    output: list[Any] = field(default_factory=list)
    id: str = "fake-response-123"
    usage: Any = None


def _item_to_dict(item: Any) -> dict[str, Any]:
    if isinstance(item, dict):
        return item
    return {
        key: getattr(item, key)
        for key in ("type", "call_id", "name", "arguments")
        if hasattr(item, key)
    }


class FakeLLMClient:
    """Deterministic LLMClient for tests."""

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

    def complete(
        self,
        *,
        messages: list[dict[str, Any]],
        tools: Sequence[Any],
        should_abort: Callable[[], bool] | None = None,
    ) -> LLMResponse:
        self.calls.append(
            {
                "method": "complete",
                "messages": [dict(m) for m in messages],
                "tools": [t.name for t in tools],
            }
        )
        fake = (
            self._response_sequence.pop(0)
            if self._response_sequence
            else FakeResponse(output_text=self.response)
        )
        tool_calls = tuple(
            parse_tool_call(
                call_id=item.call_id,
                name=item.name,
                raw_arguments=item.arguments,
            )
            for item in fake.output
            if item.type == "function_call"
        )
        return LLMResponse(
            text=fake.output_text,
            tool_calls=tool_calls,
            usage=extract_usage(fake),
            assistant_items=tuple(_item_to_dict(i) for i in fake.output),
        )
```

---

### `app/llm/resilient_client.py` <a id="appllmresilientclientpy"></a>

```python
import time
from collections.abc import Callable, Sequence
from dataclasses import replace
from typing import Any

from app.tools import Tool

from .errors import DeadlineExceeded, LLMCallFailed
from .llm_errors import classify_llm_error, retry_after_seconds
from .retry import ErrorKind, RetryPolicy
from .types import AttemptRecord, LLMResponse


class ResilientClient:
    """Retry decorator around any LLMClient. Stateless.

    Only the LLM call is retried; tool execution never is (side effects).
    The attempt log travels on the response (or on the raised exception).
    A provider retry hint raises the wait to at least the hint; a hint
    longer than max_retry_after_seconds fails fast instead of waiting.
    """

    def __init__(
        self,
        inner: Any,
        policy: RetryPolicy,
        *,
        sleep: Callable[[float], None] = time.sleep,
        classify: Callable[[Exception], ErrorKind] = classify_llm_error,
        max_retry_after_seconds: float = 60.0,
    ) -> None:
        self._inner = inner
        self._policy = policy
        self._sleep = sleep
        self._classify = classify
        self._max_hint = max_retry_after_seconds

    def complete(
        self,
        *,
        messages: list[dict[str, Any]],
        tools: Sequence[Tool],
        should_abort: Callable[[], bool] | None = None,
    ) -> LLMResponse:
        attempts: list[AttemptRecord] = []
        attempt = 1
        while True:
            started = time.perf_counter()
            try:
                response = self._inner.complete(messages=messages, tools=tools)
                return replace(response, attempts=tuple(attempts))
            except Exception as exc:
                latency_ms = (time.perf_counter() - started) * 1000
                kind = self._classify(exc)
                decision = self._policy.decide(attempt=attempt, error_kind=kind)

                hint = (
                    retry_after_seconds(exc)
                    if kind == ErrorKind.TRANSIENT
                    else None
                )
                should_retry = decision.should_retry
                reason = decision.reason
                delay = decision.delay_seconds

                if should_retry and hint is not None:
                    if hint > self._max_hint:
                        should_retry = False
                        reason = (
                            f"retry-after {hint:.1f}s exceeds "
                            f"max wait {self._max_hint:.1f}s"
                        )
                    else:
                        delay = max(delay, hint)

                attempts.append(
                    AttemptRecord(
                        attempt=attempt,
                        error=f"{type(exc).__name__}: {exc}",
                        kind=kind,
                        delay_seconds=delay if should_retry else 0.0,
                        retry_after_seconds=hint,
                        latency_ms=latency_ms,
                    )
                )

                if not should_retry:
                    raise LLMCallFailed(
                        f"LLM call failed ({reason}) "
                        f"after {attempt} attempt(s): {exc}",
                        attempts=attempt,
                        kind=kind,
                        attempt_log=tuple(attempts),
                    ) from exc

                if should_abort is not None and should_abort():
                    raise DeadlineExceeded(
                        "run deadline expired while retrying LLM call",
                        attempt_log=tuple(attempts),
                    ) from exc

                self._sleep(delay)
                attempt += 1
```

---

### `app/llm/openai_tools.py` <a id="appllmopenaitoolspy"></a>

```python
from typing import Any

from app.tools import Tool


def to_openai_tool(tool: Tool) -> dict[str, Any]:
    """Convert an internal Tool into an OpenAI function tool."""

    return {
        "type": "function",
        "name": tool.name,
        "description": tool.description,
        "parameters": tool.input_schema,
        "strict": True,
    }
```

---

### `app/llm/__init__.py` <a id="appllminitpy"></a>

```python
from .client import LLMClient
from .errors import DeadlineExceeded, LLMCallFailed
from .fake_client import FakeLLMClient, FakeResponse
from .llm_errors import classify_llm_error, retry_after_seconds
from .openai_client import OpenAIClient
from .openai_tools import to_openai_tool
from .resilient_client import ResilientClient
from .retry import ErrorKind, RetryDecision, RetryPolicy
from .types import AttemptRecord, LLMResponse, Usage, extract_usage

__all__ = [
    "AttemptRecord",
    "DeadlineExceeded",
    "ErrorKind",
    "FakeLLMClient",
    "FakeResponse",
    "LLMCallFailed",
    "LLMClient",
    "LLMResponse",
    "OpenAIClient",
    "ResilientClient",
    "RetryDecision",
    "RetryPolicy",
    "Usage",
    "classify_llm_error",
    "extract_usage",
    "retry_after_seconds",
    "to_openai_tool",
]
```

---

### `app/tools/base.py` <a id="apptoolsbasepy"></a>

```python
from abc import ABC, abstractmethod
from typing import Any

from pydantic import BaseModel

from .schema_utils import strict_json_schema


class Tool(ABC):
    """Base abstraction for all agent tools.

    A tool declares its argument model ONCE (args_model). Both the
    model-facing JSON schema and runtime validation derive from it.
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """Unique tool name exposed to the LLM."""
        raise NotImplementedError

    @property
    @abstractmethod
    def description(self) -> str:
        """Human/model-readable description of the tool."""
        raise NotImplementedError

    @property
    @abstractmethod
    def args_model(self) -> type[BaseModel]:
        """Pydantic model describing and validating the tool's input."""
        raise NotImplementedError

    @property
    def input_schema(self) -> dict[str, Any]:
        """Model-facing JSON Schema, derived from args_model."""
        return strict_json_schema(self.args_model)

    @abstractmethod
    def run(self, arguments: dict[str, Any]) -> Any:
        """Execute the tool with validated arguments."""
        raise NotImplementedError

    def definition(self) -> dict[str, Any]:
        """Return provider-independent tool metadata."""
        return {
            "name": self.name,
            "description": self.description,
            "input_schema": self.input_schema,
        }
```

---

### `app/tools/call.py` <a id="apptoolscallpy"></a>

```python
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class ToolCall:
    """Provider-independent representation of a tool request.

    If the model produced arguments that could not be parsed,
    `arguments` is empty and `parse_error` explains why. The call
    is NOT executed; the error goes back to the model as an observation.
    """

    call_id: str
    tool_name: str
    arguments: dict[str, Any]
    parse_error: str | None = None
```

---

### `app/tools/call_parsing.py` <a id="apptoolscallparsingpy"></a>

```python
import json
from typing import Any

from .call import ToolCall


def parse_tool_call(*, call_id: str, name: str, raw_arguments: str) -> ToolCall:
    """Parse provider tool-call arguments without ever raising.

    Model output is untrusted: invalid JSON or a non-object payload becomes
    a ToolCall carrying parse_error instead of crashing the run.
    """
    try:
        parsed: Any = json.loads(raw_arguments)
    except (json.JSONDecodeError, TypeError) as exc:
        return ToolCall(
            call_id=call_id,
            tool_name=name,
            arguments={},
            parse_error=f"arguments are not valid JSON: {exc}",
        )

    if not isinstance(parsed, dict):
        return ToolCall(
            call_id=call_id,
            tool_name=name,
            arguments={},
            parse_error=(
                "arguments must be a JSON object, "
                f"got {type(parsed).__name__}"
            ),
        )

    return ToolCall(call_id=call_id, tool_name=name, arguments=parsed)
```

---

### `app/tools/execution.py` <a id="apptoolsexecutionpy"></a>

```python
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class ToolExecution:
    """Record of a single tool execution."""

    tool_name: str
    arguments: dict[str, Any]
    result: Any | None
    error: str | None
    duration_ms: float

    @property
    def success(self) -> bool:
        return self.error is None
```

---

### `app/tools/workspace.py` <a id="apptoolsworkspacepy"></a>

```python
from pathlib import Path


class Workspace:
    """Resolves paths while enforcing a workspace boundary."""

    def __init__(self, root: str | Path) -> None:
        self._root = Path(root).resolve()

    @property
    def root(self) -> Path:
        return self._root

    def resolve(self, path: str) -> Path:
        candidate = (
            self._root / path
        ).resolve()

        try:
            candidate.relative_to(self._root)
        except ValueError as exc:
            raise PermissionError(
                f"Path escapes workspace: {path}"
            ) from exc

        return candidate
```

---

### `app/tools/schemas.py` <a id="apptoolsschemaspy"></a>

```python
from pydantic import BaseModel, ConfigDict, Field, field_validator


class ToolArgs(BaseModel):
    """
    Base class for all tool argument models.

    Fields here are exactly what the MODEL may choose. Budget/safety
    limits (max_bytes, max_results, ...) are NOT model-controlled; they
    are tool configuration.
    """

    model_config = ConfigDict(
        extra="forbid",
        str_strip_whitespace=True,
    )


class ListFilesArgs(ToolArgs):
    path: str = Field(
        default="",
        description=(
            "Workspace-relative directory path. "
            "Use an empty string for the workspace root."
        ),
    )


class ReadFileArgs(ToolArgs):
    path: str = Field(description="Workspace-relative file path.")

    @field_validator("path")
    @classmethod
    def validate_path(cls, value: str) -> str:
        if not value:
            raise ValueError("path must not be empty")
        return value


class SearchTextArgs(ToolArgs):
    query: str = Field(description="Text to search for.")
    path: str = Field(
        default="",
        description=(
            "Workspace-relative directory or file. "
            "Use an empty string for the workspace root."
        ),
    )

    @field_validator("query")
    @classmethod
    def validate_query(cls, value: str) -> str:
        if not value:
            raise ValueError("query must not be empty")
        return value
```

---

### `app/tools/schema_utils.py` <a id="apptoolsschemautilspy"></a>

```python
from typing import Any

from pydantic import BaseModel


def strict_json_schema(model: type[BaseModel]) -> dict[str, Any]:
    """
    Build a provider-strict JSON schema from a Pydantic model.

    Strict function-calling modes generally require:
    - additionalProperties: false
    - every property listed in `required`
    - no `title` / `default` noise

    NOTE: exact provider rules vary; verify against Groq docs.
    Nested models ($defs) are intentionally unsupported for now.
    """
    raw = model.model_json_schema()

    if "$defs" in raw:
        raise ValueError(
            f"{model.__name__}: nested models are not supported "
            "by strict_json_schema yet"
        )

    properties: dict[str, Any] = {}
    for name, spec in raw.get("properties", {}).items():
        cleaned = {
            k: v for k, v in spec.items() if k not in ("title", "default")
        }
        properties[name] = cleaned

    return {
        "type": "object",
        "properties": properties,
        "required": list(properties.keys()),
        "additionalProperties": False,
    }
```

---

### `app/tools/validation.py` <a id="apptoolsvalidationpy"></a>

```python
import json
from typing import Any

from pydantic import ValidationError


def format_validation_error(
    tool_name: str,
    error: ValidationError,
) -> dict[str, Any]:
    """Compact, LLM-readable description of a tool-argument failure."""
    errors: list[dict[str, Any]] = [
        {
            "field": ".".join(str(part) for part in item.get("loc", ())),
            "message": item.get("msg", "Invalid value"),
            "type": item.get("type", "validation_error"),
        }
        for item in error.errors()
    ]

    return {
        "error_type": "tool_argument_validation",
        "tool_name": tool_name,
        "message": f"Invalid arguments for tool '{tool_name}'.",
        "errors": errors,
    }


def format_validation_error_json(tool_name: str, error: ValidationError) -> str:
    return json.dumps(format_validation_error(tool_name, error))
```

---

### `app/tools/registry.py` <a id="apptoolsregistrypy"></a>

```python
import builtins

from .base import Tool


class ToolRegistry:
    """Stores and resolves tools by name."""

    def __init__(self) -> None:
        self._tools: dict[str, Tool] = {}

    def register(self, tool: Tool) -> None:
        if tool.name in self._tools:
            raise ValueError(
                f"Tool already registered: {tool.name}"
            )

        self._tools[tool.name] = tool

    def get(self, name: str) -> Tool:
        try:
            return self._tools[name]
        except KeyError as exc:
            raise KeyError(
                f"Unknown tool: {name}"
            ) from exc

    def list(self) -> list[Tool]:
        return list(self._tools.values())

    def definitions(self) -> builtins.list[dict]:
        return [
            tool.definition()
            for tool in self._tools.values()
        ]
```

---

### `app/tools/executor.py` <a id="apptoolsexecutorpy"></a>

```python
from time import perf_counter
from typing import Any

from pydantic import ValidationError

from .execution import ToolExecution
from .registry import ToolRegistry
from .validation import format_validation_error_json


class ToolExecutor:
    """Executes registered tools and records execution metadata."""

    def __init__(self, registry: ToolRegistry) -> None:
        self._registry = registry

    def execute(
        self,
        *,
        tool_name: str,
        arguments: dict[str, Any],
    ) -> ToolExecution:
        started_at = perf_counter()

        def elapsed_ms() -> float:
            return (perf_counter() - started_at) * 1000

        try:
            tool = self._registry.get(tool_name)

            try:
                validated = tool.args_model.model_validate(
                    arguments
                ).model_dump()
            except ValidationError as exc:
                return ToolExecution(
                    tool_name=tool_name,
                    arguments=arguments,
                    result=None,
                    error=format_validation_error_json(tool_name, exc),
                    duration_ms=elapsed_ms(),
                )

            result = tool.run(validated)

            return ToolExecution(
                tool_name=tool_name,
                arguments=arguments,
                result=result,
                error=None,
                duration_ms=elapsed_ms(),
            )

        except Exception as exc:
            return ToolExecution(
                tool_name=tool_name,
                arguments=arguments,
                result=None,
                error=str(exc),
                duration_ms=elapsed_ms(),
            )
```

---

### `app/tools/list_files.py` <a id="apptoolslistfilespy"></a>

```python
from typing import Any

from .base import Tool
from .schemas import ListFilesArgs
from .workspace import Workspace


class ListFilesTool(Tool):
    """List files and directories under the workspace."""

    def __init__(self, workspace: Workspace) -> None:
        self._workspace = workspace

    @property
    def name(self) -> str:
        return "list_files"

    @property
    def description(self) -> str:
        return (
            "List files and directories under a workspace-relative "
            "directory. Use an empty path for the workspace root."
        )

    @property
    def args_model(self) -> type[ListFilesArgs]:
        return ListFilesArgs

    def run(self, arguments: dict[str, Any]) -> list[str]:
        path = arguments["path"]
        directory = self._workspace.resolve(path)

        if not directory.exists():
            raise FileNotFoundError(
                f"Directory does not exist: {path}"
            )

        if not directory.is_dir():
            raise NotADirectoryError(
                f"Path is not a directory: {path}"
            )

        return sorted(
            entry.name
            for entry in directory.iterdir()
        )
```

---

### `app/tools/read_file.py` <a id="apptoolsreadfilepy"></a>

```python
from typing import Any

from .base import Tool
from .schemas import ReadFileArgs
from .workspace import Workspace


class ReadFileTool(Tool):
    """Read a UTF-8 text file from the workspace."""

    def __init__(
        self,
        workspace: Workspace,
        *,
        max_bytes: int = 100_000,
    ) -> None:
        self._workspace = workspace
        self._max_bytes = max_bytes

    @property
    def name(self) -> str:
        return "read_file"

    @property
    def description(self) -> str:
        return (
            "Read a UTF-8 text file from the workspace. "
            "The path must be workspace-relative."
        )

    @property
    def args_model(self) -> type[ReadFileArgs]:
        return ReadFileArgs

    def run(self, arguments: dict[str, Any]) -> dict[str, Any]:
        path = arguments["path"]
        file_path = self._workspace.resolve(path)

        if not file_path.exists():
            raise FileNotFoundError(
                f"File not found: {path}"
            )

        if not file_path.is_file():
            raise IsADirectoryError(
                f"Path is not a file: {path}"
            )

        size = file_path.stat().st_size

        if size > self._max_bytes:
            raise ValueError(
                f"File is too large to read: "
                f"{path} ({size} bytes, "
                f"limit {self._max_bytes})"
            )

        try:
            content = file_path.read_text(
                encoding="utf-8"
            )
        except UnicodeDecodeError as exc:
            raise ValueError(
                f"File is not valid UTF-8 text: {path}"
            ) from exc

        return {
            "path": path,
            "content": content,
            "size_bytes": size,
        }
```

---

### `app/tools/search_text.py` <a id="apptoolssearchtextpy"></a>

```python
import os
from pathlib import Path
from typing import Any

from .base import Tool
from .schemas import SearchTextArgs
from .workspace import Workspace

SKIP_DIRS = frozenset(
    {
        ".git",
        ".venv",
        "venv",
        "__pycache__",
        ".pytest_cache",
        ".ruff_cache",
        ".mypy_cache",
        "node_modules",
    }
)


class SearchTextTool(Tool):
    """Search for text in workspace files."""

    def __init__(
        self,
        workspace: Workspace,
        *,
        max_results: int = 50,
        max_file_bytes: int = 200_000,
    ) -> None:
        self._workspace = workspace
        self._max_results = max_results
        self._max_file_bytes = max_file_bytes

    @property
    def name(self) -> str:
        return "search_text"

    @property
    def description(self) -> str:
        return (
            "Search for a text string inside workspace files. "
            "Returns matching file paths and line numbers."
        )

    @property
    def args_model(self) -> type[SearchTextArgs]:
        return SearchTextArgs

    def run(self, arguments: dict[str, Any]) -> list[dict[str, Any]]:
        query = arguments["query"]
        path = arguments["path"]

        if not query:
            raise ValueError("Search query cannot be empty.")

        target = self._workspace.resolve(path)

        if not target.exists():
            raise FileNotFoundError(
                f"Path does not exist: {path}"
            )

        files = (
            [target]
            if target.is_file()
            else self._iter_files(target)
        )

        results: list[dict[str, Any]] = []

        for file_path in files:
            if len(results) >= self._max_results:
                break

            if file_path.stat().st_size > self._max_file_bytes:
                continue

            relative_path = file_path.relative_to(self._workspace.root)
            matches = self._search_file(file_path, relative_path, query)
            results.extend(matches)

            if len(results) >= self._max_results:
                results = results[: self._max_results]
                break

        return results

    def _search_file(
        self,
        file_path: Path,
        relative_path: Path,
        query: str,
    ) -> list[dict[str, Any]]:
        """Return matching lines from a single file."""
        try:
            lines = file_path.read_text(encoding="utf-8").splitlines()
        except (UnicodeDecodeError, OSError):
            return []

        matches: list[dict[str, Any]] = []
        query_lower = query.lower()

        for line_number, line in enumerate(lines, start=1):
            if query_lower in line.lower():
                matches.append(
                    {
                        "path": relative_path.as_posix(),
                        "line": line_number,
                        "text": line,
                    }
                )

        return matches

    def _iter_files(self, directory: Path) -> list[Path]:
        files: list[Path] = []

        for current, dirnames, filenames in os.walk(directory):
            # prune in place so os.walk never descends into skipped dirs
            dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]

            for name in filenames:
                path = Path(current) / name
                if path.is_file():
                    files.append(path)

        return sorted(files)
```

---

### `app/tools/__init__.py` <a id="apptoolsinitpy"></a>

```python
from .base import Tool
from .call import ToolCall
from .call_parsing import parse_tool_call
from .execution import ToolExecution
from .executor import ToolExecutor
from .list_files import ListFilesTool
from .read_file import ReadFileTool
from .registry import ToolRegistry
from .search_text import SearchTextTool
from .workspace import Workspace

__all__ = [
    "ListFilesTool",
    "ReadFileTool",
    "SearchTextTool",
    "Tool",
    "ToolCall",
    "ToolExecution",
    "ToolExecutor",
    "ToolRegistry",
    "Workspace",
    "parse_tool_call",
]
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

### `tests/builders.py` <a id="testsbuilderspy"></a>

```python
import json
from types import SimpleNamespace
from typing import Any

from app.llm import FakeResponse, LLMResponse, extract_usage


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


def function_call_item(
    *,
    call_id: str,
    name: str,
    arguments: str,
) -> SimpleNamespace:
    """Build a fake LLM output item that looks like a function_call."""
    return SimpleNamespace(
        type="function_call",
        call_id=call_id,
        name=name,
        arguments=arguments,
    )


class FakeClock:
    """Manually-advanced clock for deterministic tests without sleep()."""

    def __init__(self, value: float = 0.0) -> None:
        self.value = value

    def now(self) -> float:
        return self.value


class FakeSDK:
    """Fake provider SDK for testing OpenAIClient complete()."""

    def __init__(self, response: Any) -> None:
        self._response = response
        self.calls: list[dict[str, Any]] = []
        self.responses = SimpleNamespace(create=self._create)

    def _create(self, **kwargs: Any) -> Any:
        self.calls.append(kwargs)
        return self._response


class ScriptedClient:
    """Raises or returns items from a preconfigured script, one per call."""

    def __init__(self, script: list[Any]) -> None:
        self._script = list(script)
        self.calls = 0

    def complete(self, *, messages: Any, tools: Any, should_abort: Any = None) -> Any:
        self.calls += 1
        item = self._script.pop(0)
        if isinstance(item, Exception):
            raise item
        if isinstance(item, FakeResponse):
            return LLMResponse(
                text=item.output_text,
                tool_calls=(),
                usage=extract_usage(item),
            )
        return item
```

---
