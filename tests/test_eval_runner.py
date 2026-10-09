import json
from pathlib import Path

from app.agent import AgentLoop, AgentStatus
from app.llm import FakeLLMClient
from app.tools import ReadFileTool, ToolExecutor, ToolRegistry, Workspace
from evals.compare import compare
from evals.runner import (
    build_report,
    category_pass_rates,
    cooldown_for,
    read_paths_from,
    run_suite,
    run_task_once,
    summarize,
)
from evals.spec import load_tasks
from tests.builders import final_response, tool_call_response

ROOT = Path(__file__).resolve().parents[1]
SPEC = load_tasks(ROOT / "evals" / "tasks.yaml")
FIXTURE = ROOT / SPEC.fixture
TASK = {t.id: t for t in SPEC.tasks}


def good_client() -> FakeLLMClient:
    return FakeLLMClient(
        response="x",
        response_sequence=[
            tool_call_response("c1", "read_file", {"path": "src/config.py"}),
            final_response("The maximum is 20 items."),
        ],
    )


def lazy_client() -> FakeLLMClient:
    return FakeLLMClient(
        response="x", response_sequence=[final_response("The maximum is 20 items.")]
    )


def test_passing_run_is_graded_pass() -> None:
    rec = run_task_once(TASK["read-max-items"], 1, FIXTURE, good_client)
    assert rec.passed
    assert rec.score == 1.0
    assert rec.status == AgentStatus.COMPLETED.value


def test_answer_without_reading_is_caught() -> None:
    rec = run_task_once(TASK["read-max-items"], 1, FIXTURE, lazy_client)
    assert not rec.passed
    assert rec.failed_checks == ["must_read"]


def test_failed_read_does_not_count_as_read() -> None:
    def client() -> FakeLLMClient:
        return FakeLLMClient(
            response="x",
            response_sequence=[
                tool_call_response("c1", "read_file", {"path": "src/nope.py"}),
                final_response("The maximum is 20 items."),
            ],
        )

    rec = run_task_once(TASK["read-max-items"], 1, FIXTURE, client)
    assert "must_read" in rec.failed_checks


def test_fixture_is_never_modified(tmp_path: Path) -> None:
    before = {
        p: p.read_bytes()
        for p in FIXTURE.rglob("*")
        if p.is_file() and "__pycache__" not in p.parts
    }
    run_task_once(TASK["read-max-items"], 1, FIXTURE, good_client)
    after = {
        p: p.read_bytes()
        for p in FIXTURE.rglob("*")
        if p.is_file() and "__pycache__" not in p.parts
    }
    assert before == after


def test_each_run_gets_a_fresh_client() -> None:
    made: list[int] = []

    def factory() -> FakeLLMClient:
        made.append(1)
        return good_client()

    run_suite(
        SPEC,
        ROOT,
        factory,
        repeats=2,
        only=["read-max-items"],
        sleep=lambda _s: None,
    )
    assert len(made) == 2


def test_suite_runs_repeats_and_paces() -> None:
    sleeps: list[float] = []
    records = run_suite(
        SPEC,
        ROOT,
        good_client,
        repeats=3,
        only=["read-max-items"],
        cooldown_base=5.0,
        sleep=sleeps.append,
    )
    assert len(records) == 3
    assert len(sleeps) == 3
    assert all(s >= 5.0 for s in sleeps)


def test_cooldown_scales_with_tokens() -> None:
    assert cooldown_for(100, base=20.0, tpm_limit=8000) == 20.0
    assert cooldown_for(8000, base=20.0, tpm_limit=8000) == 60.0


def test_flaky_task_is_flagged() -> None:
    clients = iter([good_client, lazy_client, good_client])
    records = run_suite(
        SPEC,
        ROOT,
        lambda: next(clients)(),
        repeats=3,
        only=["read-max-items"],
        sleep=lambda _s: None,
    )
    summary = summarize(SPEC, records)[0]
    assert summary.flaky
    assert abs(summary.pass_rate - 2 / 3) < 1e-9


def test_report_structure_and_categories() -> None:
    records = run_suite(
        SPEC,
        ROOT,
        good_client,
        repeats=1,
        only=["read-max-items"],
        sleep=lambda _s: None,
    )
    report = build_report("t", SPEC, records)
    json.dumps(report)  # serializable
    assert report["overall_pass_rate"] == 1.0
    assert report["by_category"] == {"read_fact": 1.0}
    assert category_pass_rates(summarize(SPEC, records)) == {"read_fact": 1.0}


def test_unknown_task_selection_raises() -> None:
    try:
        run_suite(SPEC, ROOT, good_client, only=["nope"], sleep=lambda _s: None)
    except ValueError as exc:
        assert "no enabled tasks" in str(exc)
    else:
        raise AssertionError("expected ValueError")


def test_disabled_tasks_are_not_run() -> None:
    try:
        run_suite(
            SPEC,
            ROOT,
            good_client,
            only=["edit-add-currency-symbol"],
            sleep=lambda _s: None,
        )
    except ValueError as exc:
        assert "no enabled tasks" in str(exc)
    else:
        raise AssertionError("disabled task must not run")


def test_compare_flags_regression_and_noise() -> None:
    def rep(version: str, a: float, b: float) -> dict[str, object]:
        return {
            "version": version,
            "overall_pass_rate": 0.5,
            "total_tokens": 1,
            "tasks": [
                {"task_id": "t1", "pass_rate": a},
                {"task_id": "t2", "pass_rate": b},
            ],
        }

    text = compare(rep("v0.1", 1.0, 0.67), rep("v0.2", 0.33, 0.67))
    assert "t1: 100% -> 33%  REGRESSION" in text
    assert "t2: 67% -> 67%  same" in text


def test_read_paths_only_counts_successful_reads() -> None:
    registry = ToolRegistry()
    registry.register(ReadFileTool(Workspace(FIXTURE)))
    agent = AgentLoop(
        client=FakeLLMClient(
            response="x",
            response_sequence=[
                tool_call_response("a", "read_file", {"path": "src/config.py"}),
                tool_call_response("b", "read_file", {"path": "src/missing.py"}),
                final_response("done"),
            ],
        ),
        registry=registry,
        executor=ToolExecutor(registry),
    )
    assert read_paths_from(agent.run("go")) == frozenset({"src/config.py"})


def test_report_carries_eval_version_and_label() -> None:
    records = run_suite(
        SPEC,
        ROOT,
        good_client,
        repeats=1,
        only=["read-max-items"],
        sleep=lambda _s: None,
    )
    report = build_report("t", SPEC, records, agent_label="prompt-a")
    assert report["eval_version"] == 2
    assert report["agent_label"] == "prompt-a"


def test_compare_warns_when_eval_version_differs() -> None:
    def rep(v: str, ev: int | None) -> dict[str, object]:
        d: dict[str, object] = {
            "version": v,
            "overall_pass_rate": 0.5,
            "total_tokens": 1,
            "tasks": [{"task_id": "t1", "pass_rate": 1.0}],
        }
        if ev is not None:
            d["eval_version"] = ev
        return d

    text = compare(rep("v0.1", None), rep("v0.2", 2))
    assert text.startswith("WARNING: eval_version 1 -> 2")
    assert not compare(rep("a", 2), rep("b", 2)).startswith("WARNING")
