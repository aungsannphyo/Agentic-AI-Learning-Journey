from pathlib import Path

import pytest

from app.agent import AgentLoop, JsonlFileSink, LoopGuard
from app.llm import FakeLLMClient
from app.tools import ListFilesTool, ToolExecutor, ToolRegistry, Workspace
from app.trace_view import (
    load_events,
    main,
    render,
    run_ids,
    select_run,
    summarize,
)
from tests.builders import final_response, tool_call_response


def _run(path: Path, *, repeat_calls: int = 1, guard: bool = False) -> str | None:
    registry = ToolRegistry()
    registry.register(ListFilesTool(Workspace(Path.cwd())))
    sequence = [
        tool_call_response(f"c{i}", "list_files", {"path": "."})
        for i in range(repeat_calls)
    ] + [final_response("done")]
    agent = AgentLoop(
        client=FakeLLMClient(response="x", response_sequence=sequence),
        registry=registry,
        executor=ToolExecutor(registry),
        trace=JsonlFileSink(path),
        loop_guard_factory=(lambda: LoopGuard(block_on_nth_call=2)) if guard else None,
    )
    return agent.run("explain the app").run_id


def test_summary_of_a_normal_run(tmp_path: Path) -> None:
    path = tmp_path / "runs.jsonl"
    run_id = _run(path)

    summary = summarize(select_run(load_events(path), run_id or ""))

    assert summary.status == "completed"
    assert summary.finished is True
    assert [r.iteration for r in summary.rows] == [0, 1]
    assert summary.rows[0].tools[0].name == "list_files"
    assert summary.rows[0].tools[0].ok is True
    assert summary.total_tokens == 4


def test_render_contains_key_facts(tmp_path: Path) -> None:
    path = tmp_path / "runs.jsonl"
    _run(path)

    text = render(summarize(select_run(load_events(path), "latest")))

    assert "status=completed" in text
    assert "list_files" in text
    assert "slowest LLM call" in text
    assert "explain the app" in text


def test_latest_and_prefix_selection(tmp_path: Path) -> None:
    path = tmp_path / "runs.jsonl"
    first = _run(path)
    second = _run(path)
    events = load_events(path)

    assert run_ids(events) == [first, second]
    assert select_run(events, "latest")[0]["run_id"] == second
    assert select_run(events, (first or "")[:12])[0]["run_id"] == first


def test_unknown_and_ambiguous_ids_raise(tmp_path: Path) -> None:
    path = tmp_path / "runs.jsonl"
    _run(path)
    _run(path)
    events = load_events(path)

    with pytest.raises(LookupError, match="no run matches"):
        select_run(events, "zzzzzz")
    with pytest.raises(LookupError, match="ambiguous"):
        select_run(events, "")


def test_guard_trip_is_shown(tmp_path: Path) -> None:
    path = tmp_path / "runs.jsonl"
    _run(path, repeat_calls=4, guard=True)

    text = render(summarize(select_run(load_events(path), "latest")))

    assert "status=loop_detected" in text
    assert "guard: loop_guard" in text


def test_truncated_trace_is_flagged(tmp_path: Path) -> None:
    path = tmp_path / "runs.jsonl"
    _run(path)
    lines = path.read_text(encoding="utf-8").splitlines()
    path.write_text("\n".join(lines[:-1]) + "\n", encoding="utf-8")

    summary = summarize(select_run(load_events(path), "latest"))

    assert summary.finished is False
    assert "incomplete" in summary.status
    assert "no run_finished" in render(summary)


def test_malformed_line_is_skipped(tmp_path: Path, capsys) -> None:
    path = tmp_path / "runs.jsonl"
    _run(path)
    with path.open("a", encoding="utf-8") as handle:
        handle.write("{not json\n")

    events = load_events(path)

    assert "skipping malformed line" in capsys.readouterr().err
    assert events


def test_old_trace_without_attempt_log_still_renders() -> None:
    events = [
        {"run_id": "r", "seq": 1, "ts": "2026-10-07T10:00:00+00:00",
         "type": "run_started", "prompt": "p"},
        {"run_id": "r", "seq": 2, "ts": "2026-10-07T10:00:01+00:00",
         "type": "llm_call", "iteration": 0, "latency_ms": 900.0,
         "input_tokens": 10, "output_tokens": 5, "attempts": 3},
        {"run_id": "r", "seq": 3, "ts": "2026-10-07T10:00:02+00:00",
         "type": "run_finished", "status": "completed", "iterations": 0,
         "error": None, "total_tokens": 15, "cost_usd": None},
    ]

    summary = summarize(events)

    assert summary.retries == 2
    assert summary.wall_ms == pytest.approx(2000.0)
    assert "cost_usd=-" in render(summary)


def test_cli_exit_codes(tmp_path: Path, capsys) -> None:
    path = tmp_path / "runs.jsonl"
    _run(path)

    assert main(["latest", "--file", str(path)]) == 0
    assert "status=completed" in capsys.readouterr().out
    assert main(["nope", "--file", str(path)]) == 1
    assert main(["--file", str(tmp_path / "missing.jsonl")]) == 1
