from pathlib import Path

import pytest

from app.agent import AgentLoop, AgentStatus, InMemorySink
from app.llm import FakeLLMClient, FakeResponse
from app.tools import ListFilesTool, ToolExecutor, ToolRegistry, Workspace


def _call(i: int, path: str = "") -> dict:
    return {
        "type": "function_call",
        "call_id": f"c{i}",
        "name": "list_files",
        "arguments": f'{{"path": "{path}"}}',
    }


def _loop(
    client: FakeLLMClient,
    tmp_path: Path,
    sink: InMemorySink,
    **kwargs,
) -> AgentLoop:
    registry = ToolRegistry()
    registry.register(ListFilesTool(Workspace(tmp_path)))
    return AgentLoop(
        client=client,
        registry=registry,
        executor=ToolExecutor(registry),
        trace=sink,
        **kwargs,
    )


def test_ledger_disabled_by_default(tmp_path: Path) -> None:
    client = FakeLLMClient(
        "unused",
        response_sequence=[FakeResponse("", [_call(1)]), FakeResponse("done")],
    )
    sink = InMemorySink()
    _loop(client, tmp_path, sink).run("q")
    assert "ledger_added" not in sink.types()


def test_ledger_with_no_reportable_facts_adds_nothing(tmp_path: Path) -> None:
    # list_files is neither a read nor a search nor a failure → nothing to say
    client = FakeLLMClient(
        "unused",
        response_sequence=[FakeResponse("", [_call(1)]), FakeResponse("done")],
    )
    sink = InMemorySink()
    _loop(client, tmp_path, sink, ledger_every=1).run("q")
    assert "ledger_added" not in sink.types()


def test_ledger_injected_after_failure_and_seen_by_next_call(tmp_path: Path) -> None:
    bad = {
        "type": "function_call",
        "call_id": "c1",
        "name": "list_files",
        "arguments": '{"path": "missing_dir"}',
    }
    client = FakeLLMClient(
        "unused",
        response_sequence=[FakeResponse("", [bad]), FakeResponse("done")],
    )
    sink = InMemorySink()
    state = _loop(client, tmp_path, sink, ledger_every=1).run("q")

    assert state.status == AgentStatus.COMPLETED
    assert "ledger_added" in sink.types()
    last_messages = client.calls[-1]["messages"]
    assert last_messages[-1]["kind"] == "user"
    assert "System note (not from the user)" in last_messages[-1]["text"]
    assert "Failed calls" in last_messages[-1]["text"]


def test_ledger_every_must_be_positive(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="ledger_every must be >= 1"):
        _loop(FakeLLMClient("x"), tmp_path, InMemorySink(), ledger_every=0)


def test_ledger_respects_every_n_cadence(tmp_path: Path) -> None:
    """With ledger_every=2, ledger fires after iter 2 but not iter 1."""
    bad = {
        "type": "function_call",
        "call_id": "c1",
        "name": "list_files",
        "arguments": '{"path": "no_dir"}',
    }
    bad2 = {**bad, "call_id": "c2"}
    client = FakeLLMClient(
        "unused",
        response_sequence=[
            FakeResponse("", [bad]),   # iter 1 – no ledger yet (1 % 2 != 0)
            FakeResponse("", [bad2]),  # iter 2 – ledger fires
            FakeResponse("done"),
        ],
    )
    sink = InMemorySink()
    _loop(client, tmp_path, sink, ledger_every=2).run("q")
    events = [e for e in sink.events if e.type == "ledger_added"]
    assert len(events) == 1
    assert events[0].data["iteration"] == 2
