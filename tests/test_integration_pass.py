import json
from pathlib import Path
from types import SimpleNamespace

import httpx
import openai
import pytest

from app.agent import AgentLoop, AgentStatus
from app.agent.llm_errors import classify_llm_error
from app.agent.resilient_client import ResilientClient
from app.agent.retry import ErrorKind, RetryPolicy
from app.llm import FakeLLMClient, FakeResponse
from app.tools import (
    ListFilesTool, ReadFileTool, SearchTextTool,
    ToolExecutor, ToolRegistry, Workspace,
)


# ── helpers ────────────────────────────────────────────────────────────────
def _request() -> httpx.Request:
    return httpx.Request("POST", "https://example.invalid/v1/responses")


def _rate_limit() -> openai.RateLimitError:
    resp = httpx.Response(429, request=_request())
    return openai.RateLimitError("rate limited", response=resp, body=None)


def _bad_request() -> openai.BadRequestError:
    resp = httpx.Response(400, request=_request())
    return openai.BadRequestError("bad request", response=resp, body=None)


class ScriptedClient:
    """Raises/returns items from a script, one per call."""

    def __init__(self, script: list) -> None:
        self._script = list(script)
        self.calls = 0

    def respond_with_tools(self, *, conversation, tools):
        self.calls += 1
        item = self._script.pop(0)
        if isinstance(item, Exception):
            raise item
        return item, []


def _ok(text: str = "ok") -> FakeResponse:
    return FakeResponse(
        output_text=text, output=[],
        usage=SimpleNamespace(input_tokens=1, output_tokens=1),
    )


def _loop(client) -> AgentLoop:
    ws = Workspace(Path.cwd())
    registry = ToolRegistry()
    registry.register(ListFilesTool(ws))
    registry.register(ReadFileTool(ws))
    registry.register(SearchTextTool(ws))
    executor = ToolExecutor(registry)
    return AgentLoop(client=client, registry=registry, executor=executor)


# ── classification ─────────────────────────────────────────────────────────
def test_rate_limit_is_transient() -> None:
    assert classify_llm_error(_rate_limit()) == ErrorKind.TRANSIENT


def test_timeout_and_connection_are_transient() -> None:
    assert classify_llm_error(openai.APITimeoutError(
        request=_request())) == ErrorKind.TRANSIENT
    assert classify_llm_error(openai.APIConnectionError(
        request=_request())) == ErrorKind.TRANSIENT


def test_bad_request_and_unknown_are_permanent() -> None:
    assert classify_llm_error(_bad_request()) == ErrorKind.PERMANENT
    assert classify_llm_error(RuntimeError("???")) == ErrorKind.PERMANENT


# ── retry behaviour (no real sleep) ────────────────────────────────────────
def test_transient_error_is_retried_with_backoff() -> None:
    sleeps: list[float] = []
    inner = ScriptedClient([_rate_limit(), _rate_limit(), _ok("done")])
    client = ResilientClient(
        inner, RetryPolicy(max_attempts=3, base_delay_seconds=0.5),
        sleep=sleeps.append,
    )

    state = _loop(client).run("hi")

    assert state.status == AgentStatus.COMPLETED
    assert state.final_response == "done"
    assert inner.calls == 3
    assert sleeps == [0.5, 1.0]          # exponential


def test_permanent_error_is_not_retried() -> None:
    sleeps: list[float] = []
    inner = ScriptedClient([_bad_request(), _ok()])
    client = ResilientClient(inner, RetryPolicy(), sleep=sleeps.append)

    state = _loop(client).run("hi")

    assert state.status == AgentStatus.LLM_FAILED
    assert inner.calls == 1
    assert sleeps == []


def test_retry_budget_exhausted_ends_llm_failed() -> None:
    inner = ScriptedClient([_rate_limit()] * 3)
    client = ResilientClient(
        inner, RetryPolicy(max_attempts=3), sleep=lambda _s: None
    )

    state = _loop(client).run("hi")

    assert state.status == AgentStatus.LLM_FAILED
    assert inner.calls == 3
    assert "retry budget exhausted" in (state.error or "")


def test_deadline_expiry_during_retry_raises_deadline_exceeded() -> None:
    from app.agent.resilient_client import DeadlineExceeded

    inner = ScriptedClient([_rate_limit(), _ok()])
    client = ResilientClient(
        inner, RetryPolicy(max_attempts=3), sleep=lambda _s: None
    )
    client.set_deadline_check(lambda: True)

    with pytest.raises(DeadlineExceeded):
        client.respond_with_tools(conversation=[], tools=[])

    assert inner.calls == 1  # never retried


def test_loop_maps_deadline_exceeded_to_timeout() -> None:
    from app.agent.resilient_client import DeadlineExceeded

    class RaisesDeadline:
        def respond_with_tools(self, *, conversation, tools):
            raise DeadlineExceeded("x")

    state = _loop(RaisesDeadline()).run("hi")

    assert state.status == AgentStatus.TIMEOUT


# ── validation wired into executor ─────────────────────────────────────────
def test_invalid_args_become_structured_observation_not_execution() -> None:
    ws = Workspace(Path.cwd())
    registry = ToolRegistry()
    registry.register(ReadFileTool(ws))
    executor = ToolExecutor(registry)

    result = executor.execute(
        tool_name="read_file",
        arguments={"path": "app/main.py", "max_bytes": -1},
    )

    assert result.success is False
    payload = json.loads(result.error)
    assert payload["error_type"] == "tool_argument_validation"
    assert payload["errors"][0]["field"] == "max_bytes"


def test_unknown_argument_is_rejected_when_validation_enabled() -> None:
    ws = Workspace(Path.cwd())
    registry = ToolRegistry()
    registry.register(ListFilesTool(ws))
    executor = ToolExecutor(registry)

    result = executor.execute(
        tool_name="list_files",
        arguments={"path": ".", "recursive": True},
    )

    assert result.success is False
    assert "recursive" in result.error
