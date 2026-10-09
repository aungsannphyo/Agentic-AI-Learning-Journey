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
    """Files successfully read via read_file (failed reads do not count)."""
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
    pricing: ModelPricing | None,
    max_tokens: int,
    wall_seconds: float,
    trace: TraceSink | None,
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
        runtime_budget=RuntimeBudget(max_wall_time_seconds=wall_seconds),
        token_budget=TokenBudget(max_total_tokens=max_tokens),
        pricing=pricing,
        trace=trace,
    )


def run_task_once(
    task: Task,
    repeat: int,
    fixture: Path,
    client_factory: ClientFactory,
    *,
    pricing: ModelPricing | None = None,
    max_tokens: int = 40_000,
    wall_seconds: float = 180.0,
    trace: TraceSink | None = None,
) -> RunRecord:
    with tempfile.TemporaryDirectory(prefix="eval_ws_") as tmp:
        workspace = Path(tmp) / "ws"
        shutil.copytree(
            fixture, workspace, ignore=shutil.ignore_patterns("__pycache__")
        )
        agent = _build_agent(
            client_factory(), workspace, task, pricing=pricing,
            max_tokens=max_tokens, wall_seconds=wall_seconds, trace=trace,
        )
        started = time.perf_counter()
        state = agent.run(task.prompt)
        wall = time.perf_counter() - started

        graded = grade(task, to_run_result(state, fixture, workspace))
        report = state.usage.report()

    return RunRecord(
        task_id=task.id,
        repeat=repeat,
        status=state.status.value,
        passed=graded.passed,
        score=graded.score,
        failed_checks=[c.name for c in graded.checks if not c.passed],
        answer=(state.final_response or "")[:600],
        iterations=state.iteration,
        total_tokens=report["total_tokens"],
        cost_usd=report["cost_usd"],
        wall_s=round(wall, 3),
        retries=len(state.llm_attempts),
        run_id=state.run_id,
    )


def cooldown_for(
    tokens_used: int, *, base: float, tpm_limit: int
) -> float:
    """Seconds to wait so the next run starts in a fresh token window."""
    return max(base, tokens_used / tpm_limit * 60.0)


def run_suite(
    spec: TaskFile,
    root: Path,
    client_factory: ClientFactory,
    *,
    repeats: int = 3,
    only: list[str] | None = None,
    cooldown_base: float = 20.0,
    tpm_limit: int = 8000,
    sleep: Callable[[float], None] = time.sleep,
    pricing: ModelPricing | None = None,
    trace: TraceSink | None = None,
    on_record: Callable[[RunRecord], None] | None = None,
) -> list[RunRecord]:
    fixture = root / spec.fixture
    tasks = [t for t in spec.enabled_tasks() if only is None or t.id in only]
    if not tasks:
        raise ValueError("no enabled tasks selected")

    records: list[RunRecord] = []
    for task in tasks:
        for repeat in range(1, repeats + 1):
            record = run_task_once(
                task, repeat, fixture, client_factory,
                pricing=pricing, trace=trace,
            )
            records.append(record)
            if on_record is not None:
                on_record(record)
            sleep(cooldown_for(
                record.total_tokens, base=cooldown_base, tpm_limit=tpm_limit
            ))
    return records


def summarize(spec: TaskFile, records: list[RunRecord]) -> list[TaskSummary]:
    by_id = {t.id: t for t in spec.tasks}
    grouped: dict[str, list[RunRecord]] = {}
    for rec in records:
        grouped.setdefault(rec.task_id, []).append(rec)

    out: list[TaskSummary] = []
    for task_id, runs in grouped.items():
        passes = [r.passed for r in runs]
        statuses: dict[str, int] = {}
        for r in runs:
            statuses[r.status] = statuses.get(r.status, 0) + 1
        out.append(TaskSummary(
            task_id=task_id,
            category=by_id[task_id].category,
            runs=len(runs),
            pass_rate=sum(passes) / len(runs),
            score_mean=sum(r.score for r in runs) / len(runs),
            flaky=0 < sum(passes) < len(runs),
            mean_tokens=sum(r.total_tokens for r in runs) / len(runs),
            mean_wall_s=sum(r.wall_s for r in runs) / len(runs),
            statuses=statuses,
        ))
    return out


def category_pass_rates(summaries: list[TaskSummary]) -> dict[str, float]:
    buckets: dict[str, list[float]] = {}
    for s in summaries:
        buckets.setdefault(s.category, []).append(s.pass_rate)
    return {c: sum(v) / len(v) for c, v in sorted(buckets.items())}


def build_report(
    version: str,
    spec: TaskFile,
    records: list[RunRecord],
    *,
    agent_label: str = "",
) -> dict[str, Any]:
    summaries = summarize(spec, records)
    costs = [r.cost_usd for r in records if r.cost_usd is not None]
    return {
        "version": version,
        "eval_version": EVAL_VERSION,
        "agent_label": agent_label,
        "runs": len(records),
        "overall_pass_rate": (
            sum(r.passed for r in records) / len(records) if records else 0.0
        ),
        "total_tokens": sum(r.total_tokens for r in records),
        "total_cost_usd": round(sum(costs), 6) if costs else None,
        "by_category": category_pass_rates(summaries),
        "tasks": [asdict(s) for s in summaries],
        "records": [asdict(r) for r in records],
    }
