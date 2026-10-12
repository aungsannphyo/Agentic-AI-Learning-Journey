from pathlib import Path
from typing import Any

import pytest

from app.agent import AgentLoop, AgentStatus, InMemorySink
from app.llm import FakeLLMClient, FakeResponse
from app.tools import ListFilesTool, ToolExecutor, ToolRegistry, Workspace


def _bad(i: int) -> dict[str, Any]:
    return {
        "type": "function_call",
        "call_id": f"c{i}",
        "name": "list_files",
        "arguments": '{"path": "missing"}',
    }


def _loop(client: Any, tmp_path: Path, sink: InMemorySink, **kw: Any) -> AgentLoop:
    registry = ToolRegistry()
    registry.register(ListFilesTool(Workspace(tmp_path)))
    return AgentLoop(
        client=client,
        registry=registry,
        executor=ToolExecutor(registry),
        trace=sink,
        **kw,
    )


def test_empty_answer_fails_by_default(tmp_path: Path) -> None:
    client = FakeLLMClient("unused", response_sequence=[FakeResponse("")])
    state = _loop(client, tmp_path, InMemorySink()).run("q")
    assert state.status == AgentStatus.LLM_FAILED


def test_empty_answer_retried_once_then_recovers(tmp_path: Path) -> None:
    client = FakeLLMClient(
        "unused",
        response_sequence=[
            FakeResponse(""),
            FakeResponse("answer"),
        ],
    )
    sink = InMemorySink()
    state = _loop(client, tmp_path, sink, retry_empty_answer=True).run("q")
    assert state.status == AgentStatus.COMPLETED
    assert state.final_response == "answer"
    assert sink.types().count("empty_answer_nudged") == 1
    assert "neither a tool call" in client.calls[1]["messages"][-1]["text"]


def test_second_empty_answer_still_fails(tmp_path: Path) -> None:
    client = FakeLLMClient(
        "unused",
        response_sequence=[
            FakeResponse(""),
            FakeResponse(""),
        ],
    )
    state = _loop(client, tmp_path, InMemorySink(), retry_empty_answer=True).run("q")
    assert state.status == AgentStatus.LLM_FAILED


def test_empty_answer_retry_consumes_iteration_budget(tmp_path: Path) -> None:
    client = FakeLLMClient(
        "unused",
        response_sequence=[
            FakeResponse(""),
            FakeResponse("answer"),
        ],
    )
    state = _loop(
        client,
        tmp_path,
        InMemorySink(),
        retry_empty_answer=True,
        max_iterations=1,
    ).run("q")
    assert state.status == AgentStatus.MAX_ITERATIONS


def test_failure_nudge_fires_again_when_streak_grows(tmp_path: Path) -> None:
    client = FakeLLMClient(
        "unused",
        response_sequence=[
            FakeResponse("", [_bad(1)]),
            FakeResponse("", [_bad(2)]),
            FakeResponse("", [_bad(3)]),
            FakeResponse("done"),
        ],
    )
    sink = InMemorySink()
    _loop(client, tmp_path, sink, failure_nudge_after=2).run("q")
    # streak lengths 2 and 3 -> fires at 2 and again at 3 (tail grew)
    assert sink.types().count("failure_nudged") == 2


def test_failure_nudge_disabled_by_default(tmp_path: Path) -> None:
    client = FakeLLMClient(
        "unused",
        response_sequence=[
            FakeResponse("", [_bad(1)]),
            FakeResponse("", [_bad(2)]),
            FakeResponse("done"),
        ],
    )
    sink = InMemorySink()
    _loop(client, tmp_path, sink).run("q")
    assert "failure_nudged" not in sink.types()


def test_failure_nudge_after_must_be_positive(tmp_path: Path) -> None:
    with pytest.raises(ValueError):
        _loop(FakeLLMClient("x"), tmp_path, InMemorySink(), failure_nudge_after=0)
