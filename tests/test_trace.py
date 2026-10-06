import io
import json
from pathlib import Path

from app.agent import (
    AgentLoop,
    AgentStatus,
    InMemorySink,
    JsonlFileSink,
    LoopGuard,
    TraceEvent,
    TraceRecorder,
)
from app.llm import FakeLLMClient
from app.tools import ListFilesTool, ToolExecutor, ToolRegistry, Workspace
from tests.builders import final_response, tool_call_response


def _agent(client, sink, **kw) -> AgentLoop:
    registry = ToolRegistry()
    registry.register(ListFilesTool(Workspace(Path.cwd())))
    return AgentLoop(
        client=client,
        registry=registry,
        executor=ToolExecutor(registry),
        trace=sink,
        **kw,
    )


def test_happy_path_event_sequence() -> None:
    sink = InMemorySink()
    fake = FakeLLMClient(
        response="x",
        response_sequence=[
            tool_call_response("c1", "list_files", {"path": "."}),
            final_response("done"),
        ],
    )

    state = _agent(fake, sink).run("go")

    assert state.status == AgentStatus.COMPLETED
    assert sink.types() == [
        "run_started", "llm_call", "tool_call", "llm_call", "run_finished",
    ]
    assert [e.seq for e in sink.events] == [1, 2, 3, 4, 5]
    assert {e.run_id for e in sink.events} == {state.run_id}


def test_tool_call_event_has_size_not_content() -> None:
    sink = InMemorySink()
    fake = FakeLLMClient(
        response="x",
        response_sequence=[
            tool_call_response("c1", "list_files", {"path": "."}),
            final_response(),
        ],
    )

    _agent(fake, sink).run("go")

    tool = next(e for e in sink.events if e.type == "tool_call")
    data = tool.to_dict()
    assert data["tool_name"] == "list_files"
    assert data["arguments"] == {"path": "."}
    assert data["success"] is True
    assert data["result_chars"] > 0
    assert "result" not in data


def test_tool_error_is_traced_as_failure() -> None:
    sink = InMemorySink()
    fake = FakeLLMClient(
        response="x",
        response_sequence=[
            tool_call_response("c1", "list_files", {"path": "nope_dir"}),
            final_response(),
        ],
    )

    _agent(fake, sink).run("go")

    tool = next(e for e in sink.events if e.type == "tool_call")
    assert tool.data["success"] is False
    assert tool.data["error"]


def test_guard_trip_is_traced() -> None:
    sink = InMemorySink()
    fake = FakeLLMClient(
        response="x",
        response_sequence=[
            tool_call_response(f"c{i}", "list_files", {"path": "."})
            for i in range(5)
        ],
    )

    state = _agent(
        fake, sink, loop_guard_factory=lambda: LoopGuard(block_on_nth_call=2)
    ).run("go")

    assert state.status == AgentStatus.LOOP_DETECTED
    guard = next(e for e in sink.events if e.type == "guard_triggered")
    assert guard.data["guard"] == "loop_guard"
    assert sink.events[-1].type == "run_finished"
    assert sink.events[-1].data["status"] == "loop_detected"


def test_malformed_call_is_traced() -> None:
    sink = InMemorySink()
    fake = FakeLLMClient(
        response="x",
        response_sequence=[
            tool_call_response("c1", "list_files", "{bad"),
            final_response(),
        ],
    )

    _agent(fake, sink).run("go")

    tool = next(e for e in sink.events if e.type == "tool_call")
    assert tool.data["success"] is False
    assert "malformed" in tool.data["error"]


def test_run_finished_carries_totals() -> None:
    sink = InMemorySink()
    fake = FakeLLMClient(response="x", response_sequence=[final_response("ok")])

    _agent(fake, sink).run("go")

    finished = sink.events[-1].data
    assert finished["status"] == "completed"
    assert finished["total_tokens"] == 2


def test_no_sink_means_no_overhead_and_no_run_id() -> None:
    fake = FakeLLMClient(response="x", response_sequence=[final_response()])

    state = _agent(fake, None).run("go")

    assert state.run_id is None
    assert state.status == AgentStatus.COMPLETED


def test_failing_sink_does_not_break_the_run() -> None:
    class Broken:
        def write(self, event: TraceEvent) -> None:
            raise OSError("disk full")

    fake = FakeLLMClient(response="x", response_sequence=[final_response()])

    state = _agent(fake, Broken()).run("go")

    assert state.status == AgentStatus.COMPLETED


def test_recorder_reports_sink_failure_to_stderr_stream() -> None:
    class Broken:
        def write(self, event: TraceEvent) -> None:
            raise OSError("disk full")

    err = io.StringIO()
    TraceRecorder(Broken(), err=err).emit("x")

    assert "trace sink failed" in err.getvalue()


def test_jsonl_sink_writes_one_parseable_line_per_event(tmp_path: Path) -> None:
    path = tmp_path / "t" / "runs.jsonl"
    fake = FakeLLMClient(
        response="x",
        response_sequence=[
            tool_call_response("c1", "list_files", {"path": "."}),
            final_response(),
        ],
    )

    _agent(fake, JsonlFileSink(path)).run("go")

    lines = path.read_text(encoding="utf-8").splitlines()
    parsed = [json.loads(line) for line in lines]
    assert parsed[0]["type"] == "run_started"
    assert len({p["run_id"] for p in parsed}) == 1
    assert [p["seq"] for p in parsed] == list(range(1, len(parsed) + 1))


def test_two_runs_get_distinct_run_ids() -> None:
    sink = InMemorySink()
    registry = ToolRegistry()
    registry.register(ListFilesTool(Workspace(Path.cwd())))

    def run_once() -> str | None:
        fake = FakeLLMClient(response="x", response_sequence=[final_response()])
        agent = AgentLoop(
            client=fake, registry=registry,
            executor=ToolExecutor(registry), trace=sink,
        )
        return agent.run("go").run_id

    assert run_once() != run_once()
