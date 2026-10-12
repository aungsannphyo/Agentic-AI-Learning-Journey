# Agent Runtime — Evaluation Subsystem Snapshot (`evals/`)

Automated benchmarking suite, task specifications, programmatic graders with refusal hardening, workspace isolation runner, pacing cooldown, and differential comparison CLI.

**Files count**: 6 files | **Active status**: 278 passed, 3 xfailed, ruff/mypy clean

## ဖိုင်များ မာတိကာ (Table of Contents)

- [`evals/__init__.py`](#evalsinitpy)
- [`evals/spec.py`](#evalsspecpy)
- [`evals/graders.py`](#evalsgraderspy)
- [`evals/runner.py`](#evalsrunnerpy)
- [`evals/compare.py`](#evalscomparepy)
- [`evals/run.py`](#evalsrunpy)

---

### `evals/__init__.py` <a id="evalsinitpy"></a>

```python
"""Evaluation subsystem."""
```

---

### `evals/spec.py` <a id="evalsspecpy"></a>

```python
from pathlib import Path
from typing import Literal, Self

import yaml
from pydantic import BaseModel, ConfigDict, Field, model_validator

EVAL_VERSION = 4  # bump when graders.py or tasks.yaml change meaning

Category = Literal[
    "find_file", "read_fact", "find_symbol", "explain", "negative", "edit", "positive_control"
]
ExpectKind = Literal[
    "answer_contains_all",
    "answer_contains_any",
    "file_content_contains",
    "refusal",
]


class Expect(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: ExpectKind
    values: list[str] = Field(default_factory=list)
    path: str | None = None  # file_content_contains only
    forbidden: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def _check(self) -> Self:
        if self.kind == "file_content_contains" and not self.path:
            raise ValueError("file_content_contains requires path")
        if self.kind != "file_content_contains" and self.path is not None:
            raise ValueError("path is only valid for file_content_contains")
        if self.kind != "refusal" and not self.values:
            raise ValueError(f"{self.kind} requires values")
        return self


class Task(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(pattern=r"^[a-z0-9][a-z0-9-]*$")
    category: Category
    prompt: str = Field(min_length=1)
    expect: Expect
    must_read: list[str] = Field(default_factory=list)
    unchanged: list[str] = Field(default_factory=list)
    max_iterations: int = Field(default=8, ge=1, le=30)
    enabled: bool = True


class TaskFile(BaseModel):
    model_config = ConfigDict(extra="forbid")

    version: Literal[1]
    fixture: str
    tasks: list[Task] = Field(min_length=1)

    @model_validator(mode="after")
    def _unique_ids(self) -> Self:
        ids = [t.id for t in self.tasks]
        duplicates = sorted({i for i in ids if ids.count(i) > 1})
        if duplicates:
            raise ValueError(f"duplicate task ids: {duplicates}")
        return self

    def enabled_tasks(self) -> list[Task]:
        return [t for t in self.tasks if t.enabled]


def load_tasks(path: str | Path) -> TaskFile:
    raw = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    return TaskFile.model_validate(raw)


def referenced_paths(task: Task) -> list[str]:
    """Every fixture file a task points at (must_read, unchanged, expect.path)."""
    paths = [*task.must_read, *task.unchanged]
    if task.expect.path:
        paths.append(task.expect.path)
    return paths
```

---

### `evals/graders.py` <a id="evalsgraderspy"></a>

```python
import functools
import re
from dataclasses import dataclass, field
from pathlib import Path

from .spec import Task

REFUSAL_CUES = (
    "no ", "not ", "n't", "none", "cannot", "can't", "unable",
    "without", "doesn't", "does not", "isn't", "nothing", "never",
)
PATH_LIKE = re.compile(r"[A-Za-z0-9_./-]+\.py\b")
POINTER_VERBS = re.compile(
    r"\b(?:see|check|try|refer\s+to|look\s+at)\s+(?:the\s+)?([A-Za-z0-9_./-]+(?:\s+[A-Za-z0-9_.-]+)?)",
    re.IGNORECASE,
)
POINTER_STOP_WORDS = {
    "if", "whether", "that", "this", "it", "again", "out", "all",
    "each", "every", "any", "other", "another", "more", "further",
    "details", "here", "above", "below", "there", "to", "and",
}
POINTER_ENTITY_SUFFIXES = {
    "module", "service", "helper", "client", "file", "handler",
    "class", "function", "package", "component",
}


@dataclass(frozen=True)
class RunResult:
    status: str
    answer: str
    read_paths: frozenset[str]
    fixture_dir: Path
    workspace_dir: Path | None = None


@dataclass(frozen=True)
class Check:
    name: str
    passed: bool
    detail: str = ""


@dataclass(frozen=True)
class Grade:
    passed: bool
    score: float
    checks: tuple[Check, ...] = field(default_factory=tuple)


def contains_word(text: str, value: str) -> bool:
    pattern = (
        r"(?<![A-Za-z0-9.])"
        + re.escape(value.lower())
        + r"(?![A-Za-z0-9])(?!\.\d*[1-9])"
    )
    return re.search(pattern, text.lower()) is not None


def _norm(path: str) -> str:
    return path.replace("\\", "/").lstrip("./")


def _answer_check(task: Task, result: RunResult) -> list[Check]:
    expect = task.expect
    answer = result.answer
    checks: list[Check] = []

    if expect.kind == "answer_contains_all":
        missing = [v for v in expect.values if not contains_word(answer, v)]
        checks.append(Check("answer", not missing, f"missing: {missing}" if missing else ""))
    elif expect.kind == "answer_contains_any":
        ok = any(contains_word(answer, v) for v in expect.values)
        checks.append(Check("answer", ok, "" if ok else f"none of {expect.values}"))
    elif expect.kind == "refusal":
        checks.extend(_refusal_checks(result))
    elif expect.kind == "file_content_contains":
        checks.append(_file_content_check(task, result))

    for bad in expect.forbidden:
        hit = contains_word(answer, bad)
        checks.append(Check(f"forbidden:{bad}", not hit, "mentioned" if hit else ""))
    return checks


def _is_real_path(fixture_dir: Path, path_str: str) -> bool:
    norm = _norm(path_str)
    if (fixture_dir / norm).is_file():
        return True
    if "/" not in norm and "\\" not in norm:
        return any(p.name == norm for p in fixture_dir.rglob("*.py"))
    return False


@functools.lru_cache(maxsize=16)
def _fixture_identifiers(fixture_dir: Path) -> frozenset[str]:
    import ast
    identifiers: set[str] = set()
    for p in fixture_dir.rglob("*"):
        if p.is_file():
            identifiers.add(p.name)
            identifiers.add(p.stem)
            if p.suffix == ".py":
                try:
                    tree = ast.parse(p.read_text(encoding="utf-8"))
                    for node in ast.walk(tree):
                        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                            identifiers.add(node.name)
                except Exception:
                    pass
    return frozenset(s.lower() for s in identifiers)


def _refusal_checks(result: RunResult) -> list[Check]:
    answer_lower = result.answer.lower()
    has_cue = any(cue in answer_lower for cue in REFUSAL_CUES)

    found_paths = PATH_LIKE.findall(result.answer)
    invented = [p for p in found_paths if not _is_real_path(result.fixture_dir, p)]

    known = _fixture_identifiers(result.fixture_dir)
    invented_pointers: list[str] = []
    for match in POINTER_VERBS.finditer(result.answer):
        target = match.group(1).strip()
        words = target.split()
        first = words[0].lower().rstrip(".,;:()")
        if first in POINTER_STOP_WORDS:
            continue
        cleaned = target.rstrip(".,;:()").lower()
        if cleaned in known:
            continue
        if len(words) > 1 and words[-1].lower() in POINTER_ENTITY_SUFFIXES:
            head = " ".join(words[:-1]).lower()
            if head in known:
                continue
        invented_pointers.append(target)

    all_invented = [*invented, *invented_pointers]
    return [
        Check("refusal_indicated", has_cue, "" if has_cue else "no refusal phrasing found"),
        Check(
            "no_invented_path",
            not all_invented,
            f"invented path/entity mentioned: {all_invented}" if all_invented else "",
        ),
    ]


def _file_content_check(task: Task, result: RunResult) -> Check:
    if result.workspace_dir is None or task.expect.path is None:
        return Check("file_content", False, "no workspace to inspect")
    target = result.workspace_dir / task.expect.path
    if not target.is_file():
        return Check("file_content", False, f"missing file: {task.expect.path}")
    content = target.read_text(encoding="utf-8")
    missing = [v for v in task.expect.values if v not in content]
    return Check("file_content", not missing, f"missing content: {missing}" if missing else "")


def grade(task: Task, result: RunResult) -> Grade:
    checks: list[Check] = [Check("completed", result.status == "completed")]
    if result.status != "completed":
        return Grade(passed=False, score=0.0, checks=tuple(checks))

    norm_reads = {_norm(p) for p in result.read_paths}
    for req in task.must_read:
        passed = _norm(req) in norm_reads
        checks.append(Check(f"read:{req}", passed, "" if passed else "not read"))

    checks.extend(_answer_check(task, result))

    all_passed = all(c.passed for c in checks)
    score = sum(1.0 for c in checks if c.passed) / len(checks) if checks else 0.0
    return Grade(passed=all_passed, score=score, checks=tuple(checks))
```

---

### `evals/runner.py` <a id="evalsrunnerpy"></a>

```python
import shutil
import tempfile
import time
from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from app.agent import AgentLoop, AgentState, ModelPricing, RuntimeBudget, TokenBudget, TraceSink
from app.llm import LLMClient
from app.tools import (
    ListFilesTool,
    ReadFileTool,
    SearchTextTool,
    ToolExecutor,
    ToolRegistry,
    Workspace,
)

from .graders import RunResult, grade
from .spec import EVAL_VERSION, Task, TaskFile

ClientFactory = Callable[[], LLMClient]


@dataclass(frozen=True)
class RunRecord:
    task_id: str
    repeat: int
    status: str
    passed: bool
    score: float
    failed_checks: list[str]
    answer: str
    iterations: int
    total_tokens: int
    cost_usd: float | None
    wall_s: float
    retries: int
    run_id: str | None


@dataclass
class TaskSummary:
    task_id: str
    category: str
    runs: int
    pass_rate: float
    score_mean: float
    flaky: bool
    mean_tokens: float
    mean_wall_s: float
    statuses: dict[str, int] = field(default_factory=dict)


def read_paths_from(state: AgentState) -> frozenset[str]:
    return frozenset(
        str(r.arguments.get("path", ""))
        for r in state.history.records()
        if r.tool_name == "read_file" and r.success
    )


def to_run_result(
    state: AgentState, fixture: Path, workspace: Path | None
) -> RunResult:
    return RunResult(
        status=state.status.value,
        answer=state.final_response or "",
        read_paths=read_paths_from(state),
        fixture_dir=fixture,
        workspace_dir=workspace,
    )


def _build_agent(
    client: LLMClient,
    workspace: Path,
    task: Task,
    *,
    pricing: ModelPricing | None = None,
    trace: TraceSink | None = None,
    use_plan: bool = False,
    ledger_every: int | None = None,
    failure_nudge_after: int | None = None,
    retry_empty_answer: bool = False,
    no_progress_after: int | None = None,
) -> AgentLoop:
    ws = Workspace(workspace)
    registry = ToolRegistry()
    registry.register(ListFilesTool(ws))
    registry.register(ReadFileTool(ws))
    registry.register(SearchTextTool(ws))

    return AgentLoop(
        client=client,
        registry=registry,
        executor=ToolExecutor(registry),
        max_iterations=task.max_iterations,
        runtime_budget=RuntimeBudget(max_wall_time_seconds=120.0),
        token_budget=TokenBudget(max_total_tokens=50000),
        pricing=pricing,
        trace=trace,
        use_plan=use_plan,
        ledger_every=ledger_every,
        failure_nudge_after=failure_nudge_after,
        retry_empty_answer=retry_empty_answer,
        no_progress_after=no_progress_after,
    )


def run_task_once(
    task: Task,
    fixture_dir: Path,
    client_factory: ClientFactory,
    *,
    pricing: ModelPricing | None = None,
    trace: TraceSink | None = None,
    use_plan: bool = False,
    ledger_every: int | None = None,
    failure_nudge_after: int | None = None,
    retry_empty_answer: bool = False,
    no_progress_after: int | None = None,
) -> tuple[RunResult, AgentState]:
    with tempfile.TemporaryDirectory() as tmp:
        workspace_dir = Path(tmp) / "ws"
        shutil.copytree(fixture_dir, workspace_dir)

        client = client_factory()
        agent = _build_agent(
            client,
            workspace_dir,
            task,
            pricing=pricing,
            trace=trace,
            use_plan=use_plan,
            ledger_every=ledger_every,
            failure_nudge_after=failure_nudge_after,
            retry_empty_answer=retry_empty_answer,
            no_progress_after=no_progress_after,
        )
        state = agent.run(task.prompt)
        result = to_run_result(state, fixture_dir, workspace_dir)
        return result, state


def cooldown_for(tokens: int, base: float = 20.0, target_tpm: float = 6000.0) -> float:
    needed = (tokens / target_tpm) * 60.0
    return max(base, needed)


def run_suite(
    task_file: TaskFile,
    fixture_root: Path,
    client_factory: ClientFactory,
    *,
    repeats: int = 3,
    only: list[str] | None = None,
    cooldown_base: float = 20.0,
    pricing: ModelPricing | None = None,
    trace: TraceSink | None = None,
    on_record: Callable[[RunRecord], None] | None = None,
    use_plan: bool = False,
    ledger_every: int | None = None,
    failure_nudge_after: int | None = None,
    retry_empty_answer: bool = False,
    no_progress_after: int | None = None,
) -> list[RunRecord]:
    fixture_dir = fixture_root / task_file.fixture
    tasks = [
        t for t in task_file.enabled_tasks()
        if only is None or t.id in only
    ]
    records: list[RunRecord] = []

    for task in tasks:
        for repeat in range(1, repeats + 1):
            started = time.perf_counter()
            result, state = run_task_once(
                task,
                fixture_dir,
                client_factory,
                pricing=pricing,
                trace=trace,
                use_plan=use_plan,
                ledger_every=ledger_every,
                failure_nudge_after=failure_nudge_after,
                retry_empty_answer=retry_empty_answer,
                no_progress_after=no_progress_after,
            )
            wall_s = round(time.perf_counter() - started, 2)
            gr = grade(task, result)
            rep = state.usage.report()
            failed = [c.name for c in gr.checks if not c.passed]

            record = RunRecord(
                task_id=task.id,
                repeat=repeat,
                status=result.status,
                passed=gr.passed,
                score=round(gr.score, 4),
                failed_checks=failed,
                answer=result.answer,
                iterations=state.iteration,
                total_tokens=rep["total_tokens"],
                cost_usd=rep["cost_usd"],
                wall_s=wall_s,
                retries=len(state.llm_attempts),
                run_id=state.run_id,
            )
            records.append(record)
            if on_record is not None:
                on_record(record)

            time.sleep(cooldown_for(record.total_tokens, base=cooldown_base))

    return records


def build_report(
    version: str,
    task_file: TaskFile,
    records: list[RunRecord],
    *,
    agent_label: str = "",
) -> dict[str, Any]:
    categories = {t.id: t.category for t in task_file.tasks}
    by_cat: dict[str, list[RunRecord]] = {}
    for r in records:
        by_cat.setdefault(categories.get(r.task_id, "unknown"), []).append(r)

    by_category_rates = {
        cat: round(sum(1 for r in rs if r.passed) / len(rs), 4)
        for cat, rs in by_cat.items()
    }
    overall_rate = (
        round(sum(1 for r in records if r.passed) / len(records), 4)
        if records else 0.0
    )

    return {
        "version": version,
        "eval_version": EVAL_VERSION,
        "agent_label": agent_label,
        "runs": len(records),
        "overall_pass_rate": overall_rate,
        "by_category": by_category_rates,
        "total_tokens": sum(r.total_tokens for r in records),
        "total_cost_usd": round(sum(r.cost_usd or 0.0 for r in records), 6),
        "records": [asdict(r) for r in records],
    }
```

---

### `evals/compare.py` <a id="evalscomparepy"></a>

```python
import json
from pathlib import Path
from typing import Any

THRESHOLD = 0.2


def load_report(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def compare(old: dict[str, Any], new: dict[str, Any]) -> str:
    warning: list[str] = []
    old_ev, new_ev = old.get("eval_version", 1), new.get("eval_version", 1)
    if old_ev != new_ev:
        warning = [
            (
                f"WARNING: eval_version {old_ev} -> {new_ev}: grader/tasks changed, "
                "differences are NOT purely agent changes"
            ),
            "",
        ]
    old_tasks = {t["task_id"]: t for t in old.get("tasks", [])}
    new_tasks = {t["task_id"]: t for t in new.get("tasks", [])}
    lines = [
        *warning,
        f"{old['version']} -> {new['version']}",
        (
            f"overall pass rate: {old['overall_pass_rate']:.0%} -> "
            f"{new['overall_pass_rate']:.0%}"
        ),
        f"tokens: {old['total_tokens']} -> {new['total_tokens']}",
        "",
    ]
    for task_id in sorted(set(old_tasks) | set(new_tasks)):
        a, b = old_tasks.get(task_id), new_tasks.get(task_id)
        if a is None or b is None:
            side = "only in new" if a is None else "only in old"
            lines.append(f"  {task_id}: {side}")
            continue
        delta = b["pass_rate"] - a["pass_rate"]
        mark = (
            "REGRESSION" if delta <= -THRESHOLD
            else "IMPROVED" if delta >= THRESHOLD
            else "same"
        )
        lines.append(
            f"  {task_id}: {a['pass_rate']:.0%} -> {b['pass_rate']:.0%}  {mark}"
        )
    lines.append("")
    lines.append(
        f"note: differences under {THRESHOLD:.0%} are within noise at small N"
    )
    return "\n".join(lines)
```

---

### `evals/run.py` <a id="evalsrunpy"></a>

```python
import argparse
import json
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

from app.agent import PLANNER_V1, PROMPTS, JsonlFileSink, ModelPricing, get_prompt
from app.llm import OpenAIClient, ResilientClient, RetryPolicy

from .compare import compare, load_report
from .runner import RunRecord, build_report, run_suite
from .spec import load_tasks

ROOT = Path(__file__).resolve().parents[1]


def _pricing() -> ModelPricing | None:
    raw_in = os.getenv("MODEL_INPUT_USD_PER_MTOK")
    raw_out = os.getenv("MODEL_OUTPUT_USD_PER_MTOK")
    if not raw_in or not raw_out:
        return None
    return ModelPricing(float(raw_in), float(raw_out))


def _client(system_prompt: str) -> ResilientClient:
    inner = OpenAIClient(system_prompt=system_prompt, timeout_seconds=30.0)
    return ResilientClient(
        inner,
        RetryPolicy(max_attempts=5, base_delay_seconds=3.0, max_delay_seconds=25.0),
    )


def _print_record(record: RunRecord) -> None:
    flag = "PASS" if record.passed else "FAIL"
    detail = "" if record.passed else f" failed={record.failed_checks}"
    print(
        f"[{flag}] {record.task_id} #{record.repeat} "
        f"status={record.status} tokens={record.total_tokens} "
        f"wall={record.wall_s}s{detail}",
        flush=True,
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="evals.run")
    parser.add_argument("--version", default="dev")
    parser.add_argument("--agent-label", default="", help="label for agent/prompt version")
    parser.add_argument("--prompt", default="baseline", choices=sorted(PROMPTS))
    parser.add_argument(
        "--plan",
        action="store_true",
        help="enable upfront planner (planner-v1)",
    )
    parser.add_argument("--ledger-every", type=int, default=None,
                        help="inject evidence ledger every N iterations")
    parser.add_argument("--failure-nudge", type=int, default=None)
    parser.add_argument("--retry-empty", action="store_true")
    parser.add_argument("--no-progress", type=int, default=None)
    parser.add_argument("--repeats", type=int, default=3)
    parser.add_argument("--task", action="append", help="limit to task id (repeatable)")
    parser.add_argument("--cooldown", type=float, default=20.0)
    parser.add_argument(
        "--compare",
        nargs=2,
        metavar=("OLD", "NEW"),
        help="compare two report files and exit",
    )
    args = parser.parse_args(argv)

    if args.compare:
        print(
            compare(
                load_report(Path(args.compare[0])),
                load_report(Path(args.compare[1])),
            )
        )
        return 0

    load_dotenv()
    spec = load_tasks(ROOT / "evals" / "tasks.yaml")
    prompt = get_prompt(args.prompt)
    label_parts = [prompt.label]
    if args.plan:
        label_parts.append(PLANNER_V1.label)
    if args.ledger_every:
        label_parts.append(f"ledger{args.ledger_every}")
    if args.failure_nudge:
        label_parts.append(f"fnudge{args.failure_nudge}")
    if args.retry_empty:
        label_parts.append("retryempty")
    if args.no_progress:
        label_parts.append(f"noprog{args.no_progress}")
    agent_label = args.agent_label or "+".join(label_parts)
    records = run_suite(
        spec,
        ROOT,
        lambda: _client(prompt.text),
        repeats=args.repeats,
        only=args.task,
        cooldown_base=args.cooldown,
        pricing=_pricing(),
        trace=JsonlFileSink(ROOT / "traces" / f"eval_{args.version}.jsonl"),
        on_record=_print_record,
        use_plan=args.plan,
        ledger_every=args.ledger_every,
        failure_nudge_after=args.failure_nudge,
        retry_empty_answer=args.retry_empty,
        no_progress_after=args.no_progress,
    )
    report = build_report(args.version, spec, records, agent_label=agent_label)

    out = ROOT / "evals" / "reports" / f"{args.version}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2), encoding="utf-8")

    print(
        f"\nversion: {report['version']} (eval_version={report['eval_version']}) "
        f"overall pass rate: {report['overall_pass_rate']:.0%} "
        f"({report['runs']} runs)"
    )
    for category, rate in report["by_category"].items():
        print(f"  {category}: {rate:.0%}")
    print(f"tokens={report['total_tokens']} cost_usd={report['total_cost_usd']}")
    print(f"report: {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
```
