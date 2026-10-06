import json
from pathlib import Path
from types import SimpleNamespace

import httpx
import openai

from app.agent import AgentLoop, AgentStatus, LoopGuard
from app.llm import FakeLLMClient, FakeResponse, ResilientClient, RetryPolicy
from app.tools import (
    ListFilesTool,
    ReadFileTool,
    SearchTextTool,
    ToolExecutor,
    ToolRegistry,
    Workspace,
)
from tests.builders import ScriptedClient as _Scripted
from tests.builders import tool_outputs
from tests.builders import usage as _usage


def _call(call_id: str, name: str, raw_args: str) -> FakeResponse:
    return FakeResponse(
        output_text="",
        output=[
            SimpleNamespace(
                type="function_call", call_id=call_id, name=name, arguments=raw_args
            )
        ],
        usage=_usage(),
    )


def _final(text: str = "done") -> FakeResponse:
    return FakeResponse(output_text=text, output=[], usage=_usage())


def _agent(
    client,
    *,
    max_iterations: int = 10,
    guard: bool = False,
    max_consecutive_malformed: int = 10,
) -> AgentLoop:
    ws = Workspace(Path.cwd())
    registry = ToolRegistry()
    registry.register(ListFilesTool(ws))
    registry.register(ReadFileTool(ws))
    registry.register(SearchTextTool(ws))
    return AgentLoop(
        client=client,
        registry=registry,
        executor=ToolExecutor(registry),
        max_iterations=max_iterations,
        loop_guard_factory=(
            (lambda: LoopGuard(block_on_nth_call=3)) if guard else None
        ),
        max_consecutive_malformed=max_consecutive_malformed,
    )


def _outputs(fake: FakeLLMClient, call_index: int) -> list[dict]:
    return tool_outputs(fake.calls[call_index]["messages"])


# 1. Garbage JSON arguments → recoverable observation, NOT run death
def test_garbage_json_arguments_become_observation() -> None:
    fake = FakeLLMClient(
        response="x",
        response_sequence=[_call("c1", "read_file", "{not json"), _final()],
    )
    state = _agent(fake).run("go")

    assert state.status == AgentStatus.COMPLETED
    assert len(state.history) == 1
    assert state.history.records()[0].success is False
    out = _outputs(fake, 1)
    assert out[0]["success"] is False
    assert "not valid JSON" in out[0]["error"]


# 1b. Valid JSON but not an object
def test_non_object_arguments_become_observation() -> None:
    fake = FakeLLMClient(
        response="x",
        response_sequence=[_call("c1", "read_file", '["a.py"]'), _final()],
    )
    state = _agent(fake).run("go")

    assert state.status == AgentStatus.COMPLETED
    assert "must be a JSON object" in _outputs(fake, 1)[0]["error"]


# 2. Wrong argument types → validation observation (regression)
def test_wrong_argument_types_become_validation_observation() -> None:
    fake = FakeLLMClient(
        response="x",
        response_sequence=[_call("c1", "read_file", '{"path": 123}'), _final()],
    )
    state = _agent(fake).run("go")

    assert state.status == AgentStatus.COMPLETED
    payload = json.loads(_outputs(fake, 1)[0]["error"])
    assert payload["error_type"] == "tool_argument_validation"
    assert payload["errors"][0]["field"] == "path"


# 3. Malformed calls must not trip the loop guard
def test_malformed_calls_do_not_trigger_loop_guard() -> None:
    fake = FakeLLMClient(
        response="x",
        response_sequence=[
            _call("c1", "read_file", "{bad"),
            _call("c2", "read_file", "{bad"),
            _call("c3", "read_file", "{bad"),
            _final(),
        ],
    )
    state = _agent(fake, guard=True).run("go")

    assert state.status == AgentStatus.COMPLETED


# 4. Endless malformed calls are stopped by max_iterations (known limitation)
def test_endless_malformed_calls_stop_at_max_iterations() -> None:
    fake = FakeLLMClient(
        response="x",
        response_sequence=[_call(f"c{i}", "read_file", "{bad") for i in range(10)],
    )
    state = _agent(fake, max_iterations=3, guard=True).run("go")

    assert state.status == AgentStatus.MAX_ITERATIONS
    assert len(state.history) == 3


def test_consecutive_malformed_calls_stop_the_run() -> None:
    fake = FakeLLMClient(
        response="x",
        response_sequence=[_call(f"c{i}", "read_file", "{bad") for i in range(10)],
    )
    state = _agent(fake, max_consecutive_malformed=3).run("go")

    assert state.status == AgentStatus.LOOP_DETECTED
    assert "malformed" in (state.error or "")
    assert len(state.history) == 3


def test_valid_call_resets_malformed_counter() -> None:
    fake = FakeLLMClient(
        response="x",
        response_sequence=[
            _call("c1", "read_file", "{bad"),
            _call("c2", "list_files", '{"path": "."}'),
            _call("c3", "read_file", "{bad"),
            _call("c4", "read_file", "{bad"),
            _final(),
        ],
    )
    state = _agent(fake, max_consecutive_malformed=3).run("go")

    assert state.status == AgentStatus.COMPLETED


# 5/6. Transient provider faults through the real retry stack
def _req() -> httpx.Request:
    return httpx.Request("POST", "https://example.invalid/v1/responses")


def test_timeout_then_success_is_retried() -> None:
    client = ResilientClient(
        _Scripted([openai.APITimeoutError(request=_req()), _final("ok")]),
        RetryPolicy(max_attempts=3),
        sleep=lambda _s: None,
    )
    state = _agent(client).run("go")

    assert state.status == AgentStatus.COMPLETED
    assert [r.kind.value for r in state.llm_attempts] == ["transient"]


def test_429_backoff_then_exhausted() -> None:
    sleeps: list[float] = []
    err = openai.RateLimitError(
        "rl", response=httpx.Response(429, request=_req()), body=None
    )
    client = ResilientClient(
        _Scripted([err, err, err]),
        RetryPolicy(max_attempts=3, base_delay_seconds=0.5),
        sleep=sleeps.append,
    )
    state = _agent(client).run("go")

    assert state.status == AgentStatus.LLM_FAILED
    assert sleeps == [0.5, 1.0]
