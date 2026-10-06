import json
from pathlib import Path
from types import SimpleNamespace

import httpx
import openai
import pytest

from app.agent import AgentLoop, AgentStatus
from app.llm import DeadlineExceeded, FakeResponse
from app.llm.llm_errors import classify_llm_error
from app.llm.resilient_client import ResilientClient
from app.llm.retry import ErrorKind, RetryPolicy
from app.tools import (
    ListFilesTool,
    ReadFileTool,
    SearchTextTool,
    ToolExecutor,
    ToolRegistry,
    Workspace,
)
from tests.builders import ScriptedClient


# ── helpers ────────────────────────────────────────────────────────────────
def _request() -> httpx.Request:
    return httpx.Request("POST", "https://example.invalid/v1/responses")


def _rate_limit() -> openai.RateLimitError:
    resp = httpx.Response(429, request=_request())
    return openai.RateLimitError("rate limited", response=resp, body=None)


def _bad_request() -> openai.BadRequestError:
    resp = httpx.Response(400, request=_request())
    return openai.BadRequestError("bad request", response=resp, body=None)


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
    inner = ScriptedClient([_rate_limit(), _ok()])
    client = ResilientClient(
        inner, RetryPolicy(max_attempts=3), sleep=lambda _s: None
    )
    with pytest.raises(DeadlineExceeded):
        client.complete(messages=[], tools=[], should_abort=lambda: True)

    assert inner.calls == 1  # never retried


def test_loop_maps_deadline_exceeded_to_timeout() -> None:
    class RaisesDeadline:
        def complete(self, *, messages, tools, should_abort=None):
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
    assert result.error is not None
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
    assert result.error is not None
    assert "recursive" in result.error
