from pathlib import Path
from typing import Any

import pytest

from app.agent import AgentLoop, InMemorySink
from app.llm import FakeLLMClient, FakeResponse
from app.tools import (
    ListFilesTool,
    SearchTextTool,
    ToolExecutor,
    ToolRegistry,
    Workspace,
)


def _search(i: int, q: str = "missing") -> dict[str, Any]:
    return {
        "type": "function_call",
        "call_id": f"s{i}",
        "name": "search_text",
        "arguments": f'{{"path": "", "query": "{q}_{i}"}}',
    }


def _list(i: int) -> dict[str, Any]:
    return {
        "type": "function_call",
        "call_id": f"l{i}",
        "name": "list_files",
        "arguments": '{"path": ""}',
    }


def _loop(client: Any, tmp_path: Path, sink: InMemorySink, **kw: Any) -> AgentLoop:
    (tmp_path / "hello.txt").write_text("hello world", encoding="utf-8")
    ws = Workspace(tmp_path)
    registry = ToolRegistry()
    registry.register(ListFilesTool(ws))
    registry.register(SearchTextTool(ws))
    return AgentLoop(
        client=client,
        registry=registry,
        executor=ToolExecutor(registry),
        trace=sink,
        **kw,
    )


def test_no_progress_nudge_fires_at_threshold(tmp_path: Path) -> None:
    client = FakeLLMClient(
        "unused",
        response_sequence=[
            FakeResponse("", [_search(1)]),
            FakeResponse("", [_search(2)]),
            FakeResponse("", [_search(3)]),
            FakeResponse("done"),
        ],
    )
    sink = InMemorySink()
    _loop(client, tmp_path, sink, no_progress_after=3).run("q")
    assert sink.types().count("no_progress_nudged") == 1
    last_msg = client.calls[3]["messages"][-1]["text"]
    assert "no matches" in last_msg
    assert "say so clearly in your final answer" in last_msg


def test_no_progress_nudge_does_not_fire_again_on_transparent_tool(
    tmp_path: Path,
) -> None:
    client = FakeLLMClient(
        "unused",
        response_sequence=[
            FakeResponse("", [_search(1)]),
            FakeResponse("", [_search(2)]),
            FakeResponse("", [_search(3)]),
            FakeResponse("", [_list(4)]),  # transparent tool, streak stays 3
            FakeResponse("done"),
        ],
    )
    sink = InMemorySink()
    _loop(client, tmp_path, sink, no_progress_after=3).run("q")
    # fired at search 3, transparent list_files kept streak=3 <= last_nudged(3), so no second fire
    assert sink.types().count("no_progress_nudged") == 1


def test_no_progress_nudge_disabled_by_default(tmp_path: Path) -> None:
    client = FakeLLMClient(
        "unused",
        response_sequence=[
            FakeResponse("", [_search(1)]),
            FakeResponse("", [_search(2)]),
            FakeResponse("", [_search(3)]),
            FakeResponse("done"),
        ],
    )
    sink = InMemorySink()
    _loop(client, tmp_path, sink).run("q")
    assert "no_progress_nudged" not in sink.types()


def test_no_progress_after_must_be_positive(tmp_path: Path) -> None:
    with pytest.raises(ValueError):
        _loop(FakeLLMClient("x"), tmp_path, InMemorySink(), no_progress_after=0)
