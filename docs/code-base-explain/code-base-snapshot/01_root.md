# Agent Runtime — Root & Entry Layer Snapshot

Application execution entry point, CLI trace viewer, and root pytest configuration.

**Files count**: 3 files | **Active status**: 278 passed, 3 xfailed, ruff/mypy clean

## ဖိုင်များ မာတိကာ (Table of Contents)

- [`app/main.py`](#appmainpy)
- [`app/trace_view.py`](#apptraceviewpy)
- [`conftest.py`](#conftestpy)

---

### `app/main.py` <a id="appmainpy"></a>

```python
import json
import os
import time
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

from app.agent import (
    AgentLoop,
    JsonlFileSink,
    LoopGuard,
    ModelPricing,
    RuntimeBudget,
    TokenBudget,
    get_prompt,
)
from app.agent.trace import TraceEvent
from app.llm import OpenAIClient, ResilientClient, RetryPolicy
from app.tools import (
    ListFilesTool,
    ReadFileTool,
    SearchTextTool,
    ToolExecutor,
    ToolRegistry,
    Workspace,
)
from app.tools.execution import ToolExecution


class ConsoleAndFileSink:
    """Writes structured events to JSONL file and prints live turn-by-turn progress."""

    def __init__(self, file_sink: JsonlFileSink) -> None:
        self._file_sink = file_sink

    def write(self, event: TraceEvent) -> None:
        self._file_sink.write(event)
        self._print_event(event)

    def _print_event(self, event: TraceEvent) -> None:
        etype = event.type
        data = event.data

        if etype == "run_started":
            print(f"\n🚀 [Run Started] Run ID: {event.run_id}")
            print(f"📝 Prompt: {data.get('prompt')}")
            print(f"⚙️  Max Iterations: {data.get('max_iterations')}")
            print("─" * 70)

        elif etype == "plan_created":
            steps = data.get("steps", [])
            print("📋 [Planner] Upfront Plan Created:")
            for i, step in enumerate(steps, 1):
                print(f"   {i}. {step}")
            print("─" * 70)

        elif etype == "plan_failed":
            print(f"⚠️  [Planner Failed] {data.get('reason')}")

        elif etype == "llm_call":
            iteration = data.get("iteration", 0)
            thought = data.get("thought")
            latency = data.get("latency_ms", 0.0)
            in_tok = data.get("input_tokens")
            out_tok = data.get("output_tokens")
            tool_count = data.get("tool_call_count", 0)
            print(
                f"\n🤖 [Turn {iteration}] LLM Call ({latency:.0f}ms | In: {in_tok} tok, Out: {out_tok} tok)"
            )
            if thought:
                print(f"   💭 Thought: {thought}")
            if tool_count == 0:
                print("   🎯 Decision: Final Answer (No further tool calls needed)")

        elif etype == "tool_call":
            tool = data.get("tool_name")
            args = data.get("arguments", {})
            success = data.get("success")
            duration = data.get("duration_ms", 0.0)
            status_icon = "✅" if success else "❌"
            print(
                f"   🔧 Tool: {tool}({json.dumps(args)}) {status_icon} ({duration:.1f}ms)"
            )
            if not success:
                print(f"      ❌ Error: {data.get('error')}")

        elif etype == "no_progress_nudged":
            empty_count = data.get("empty_searches", 0)
            print(
                f"   ⚠️  [No-Progress Nudge] Injected note after {empty_count} consecutive empty searches!"
            )

        elif etype == "failure_nudged":
            failures = data.get("failures", 0)
            print(
                f"   ⚠️  [Failure Nudge] Injected note after {failures} consecutive tool failures!"
            )

        elif etype == "ledger_added":
            print("   📝 [Ledger Note] Appended evidence ledger recap into conversation")

        elif etype == "guard_triggered":
            guard = data.get("guard")
            detail = data.get("detail")
            print(f"   🛑 [Guard Triggered] {guard}: {detail}")

        elif etype == "run_finished":
            status = data.get("status")
            iters = data.get("iterations")
            total_tok = data.get("total_tokens")
            cost = data.get("cost_usd", 0.0)
            print("─" * 70)
            print(
                f"🏁 [Run Finished] Status: {status} | Iterations: {iters} | Total Tokens: {total_tok} | Cost: ${cost:.5f}\n"
            )


class VerboseToolExecutor:
    """Wraps ToolExecutor to log live result previews."""

    def __init__(self, inner: ToolExecutor) -> None:
        self._inner = inner

    def execute(
        self,
        *,
        tool_name: str,
        arguments: dict[str, Any],
    ) -> ToolExecution:
        res = self._inner.execute(tool_name=tool_name, arguments=arguments)
        if res.success:
            if isinstance(res.result, list):
                count = len(res.result)
                preview = (
                    f"{count} item(s): {res.result[:3]}"
                    if count > 0
                    else "0 matches"
                )
            elif isinstance(res.result, dict) and "content" in res.result:
                preview = f"{res.result.get('size_bytes', 0)} bytes read from {res.result.get('path')}"
            else:
                preview = str(res.result)
                if len(preview) > 90:
                    preview = preview[:87] + "..."
            print(f"      📄 Observation: {preview}")
        return res


def sleep_with_progress(seconds: float) -> None:
    print(
        f"\n⏳ [Rate Limit / 429] Groq TPM limit hit! Waiting {seconds:.1f}s before auto-retrying..."
    )
    time.sleep(seconds)
    print("   🔄 Resuming execution now...\n")


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
    raw_executor = ToolExecutor(registry)
    executor = VerboseToolExecutor(raw_executor)

    runtime_budget = RuntimeBudget(
        max_wall_time_seconds=120.0,
        per_call_timeout_seconds=30.0,
    )

    inner = OpenAIClient(
        system_prompt=get_prompt(os.getenv("AGENT_PROMPT", "baseline")).text,
        timeout_seconds=runtime_budget.per_call_timeout_seconds,
    )

    client = ResilientClient(
        inner,
        RetryPolicy(
            max_attempts=5,
            base_delay_seconds=3.0,
            max_delay_seconds=25.0,
        ),
        sleep=sleep_with_progress,
    )

    file_sink = JsonlFileSink(Path("traces") / "runs.jsonl")
    sink = ConsoleAndFileSink(file_sink)

    agent = AgentLoop(
        client=client,
        registry=registry,
        executor=executor,  # type: ignore[arg-type]
        max_iterations=10,
        runtime_budget=runtime_budget,
        loop_guard_factory=lambda: LoopGuard(block_on_nth_call=3),
        token_budget=TokenBudget(
            max_total_tokens=int(os.getenv("AGENT_MAX_TOTAL_TOKENS", "50000"))
        ),
        pricing=pricing_from_env(),
        trace=sink,
    )

    state = agent.run(
        "Explain the app directory and identify the main agent loop file."
    )

    print("\n=== Final Response ===\n")
    print(state.final_response)

    print(f"\n=== Status: {state.status.value} ===")
    if state.error:
        print(state.error)

    if state.llm_attempts:
        print("\n=== LLM Retry Log ===")
        for rec in state.llm_attempts:
            print(rec)

    print("\n=== Usage Report ===")
    print(json.dumps(state.usage.report(), indent=2))


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
