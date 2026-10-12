from pathlib import Path

from app.agent import AgentLoop, AgentStatus, InMemorySink
from app.llm import FakeLLMClient, FakeResponse
from app.tools import ListFilesTool, ToolExecutor, ToolRegistry, Workspace
from app.trace_view import render, summarize


def _call() -> dict[str, str]:
    return {
        "type": "function_call",
        "call_id": "c1",
        "name": "list_files",
        "arguments": "{}",
    }


def _reasoning(text: str) -> dict[str, object]:
    return {
        "type": "reasoning",
        "summary": [],
        "content": [{"type": "reasoning_text", "text": text}],
    }


def _loop(client: FakeLLMClient, tmp_path: Path, sink: InMemorySink) -> AgentLoop:
    registry = ToolRegistry()
    registry.register(ListFilesTool(Workspace(tmp_path)))
    return AgentLoop(
        client=client,
        registry=registry,
        executor=ToolExecutor(registry),
        trace=sink,
    )


def test_reasoning_on_tool_turn_is_recorded_and_traced(tmp_path: Path) -> None:
    client = FakeLLMClient(
        "unused",
        response_sequence=[
            FakeResponse("", [_reasoning("need layout first"), _call()]),
            FakeResponse("done", [_reasoning("enough evidence")]),
        ],
    )
    sink = InMemorySink()
    state = _loop(client, tmp_path, sink).run("q")

    assert state.status == AgentStatus.COMPLETED
    assert [(t.iteration, t.text) for t in state.thoughts] == [
        (0, "need layout first"),
        (1, "enough evidence"),
    ]
    llm = [e for e in sink.events if e.type == "llm_call"]
    assert [e.data["thought"] for e in llm] == ["need layout first", "enough evidence"]


def test_final_answer_text_is_never_a_thought(tmp_path: Path) -> None:
    client = FakeLLMClient("unused", response_sequence=[FakeResponse("the answer")])
    state = _loop(client, tmp_path, InMemorySink()).run("q")
    assert state.thoughts == []
    assert state.final_response == "the answer"


def test_trace_truncates_reasoning_but_state_keeps_full_text(tmp_path: Path) -> None:
    client = FakeLLMClient(
        "unused",
        response_sequence=[
            FakeResponse("", [_reasoning("x" * 2000), _call()]),
            FakeResponse("done"),
        ],
    )
    sink = InMemorySink()
    state = _loop(client, tmp_path, sink).run("q")
    assert len(state.thoughts[0].text) == 2000
    first = next(e for e in sink.events if e.type == "llm_call")
    assert len(first.data["thought"]) == 500


def test_trace_view_renders_thought_line() -> None:
    ts = "2026-01-01T00:00:0{}+00:00"
    events = [
        {"run_id": "r", "seq": 1, "ts": ts.format(0), "type": "run_started", "prompt": "p"},
        {
            "run_id": "r",
            "seq": 2,
            "ts": ts.format(1),
            "type": "llm_call",
            "iteration": 0,
            "latency_ms": 10.0,
            "thought": "check config first",
            "tool_call_count": 1,
        },
        {"run_id": "r", "seq": 3, "ts": ts.format(2), "type": "run_finished", "status": "completed"},
    ]
    assert "thought: check config first" in render(summarize(events))
