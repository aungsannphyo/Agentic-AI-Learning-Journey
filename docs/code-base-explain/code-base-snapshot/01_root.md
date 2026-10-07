# Agent Runtime — Root & Entry Layer Snapshot

Application execution entry point, CLI trace viewer, and root pytest configuration.

**Files count**: 3 files | **Active status**: 151 tests passed, ruff/mypy clean

## ဖိုင်များ မာတိကာ (Table of Contents)

- [`app/main.py`](#appmainpy)
- [`app/trace_view.py`](#apptraceviewpy)
- [`conftest.py`](#conftestpy)

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
