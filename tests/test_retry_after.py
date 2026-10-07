from pathlib import Path

import httpx
import openai
import pytest

from app.agent import AgentLoop, AgentStatus, InMemorySink
from app.llm import (
    LLMCallFailed,
    ResilientClient,
    RetryPolicy,
    retry_after_seconds,
)
from app.tools import ListFilesTool, ToolExecutor, ToolRegistry, Workspace
from tests.builders import ScriptedClient, llm_response

_REQ = httpx.Request("POST", "https://example.invalid/v1/responses")


def _rate_limit(message: str = "rl", headers: dict[str, str] | None = None):
    response = httpx.Response(429, headers=headers or {}, request=_REQ)
    return openai.RateLimitError(message, response=response, body=None)


def test_header_is_preferred() -> None:
    err = _rate_limit("try again in 99s", {"retry-after": "7"})
    assert retry_after_seconds(err) == 7.0


def test_message_phrase_seconds() -> None:
    err = _rate_limit("Rate limit reached. Please try again in 20.085s.")
    assert retry_after_seconds(err) == pytest.approx(20.085)


def test_message_phrase_minutes_and_seconds() -> None:
    assert retry_after_seconds(_rate_limit("try again in 1m30.5s")) == pytest.approx(90.5)


def test_message_phrase_milliseconds() -> None:
    assert retry_after_seconds(_rate_limit("try again in 250ms")) == pytest.approx(0.25)


def test_no_hint_returns_none() -> None:
    assert retry_after_seconds(_rate_limit("rl")) is None
    assert retry_after_seconds(RuntimeError("boom")) is None


def test_unparseable_header_falls_back_to_message() -> None:
    err = _rate_limit("try again in 3s", {"retry-after": "soon"})
    assert retry_after_seconds(err) == pytest.approx(3.0)


def _client(script, sleeps: list[float], **kw) -> ResilientClient:
    return ResilientClient(
        ScriptedClient(script),
        RetryPolicy(max_attempts=3, base_delay_seconds=3.0, max_delay_seconds=25.0),
        sleep=sleeps.append,
        **kw,
    )


def test_hint_larger_than_backoff_is_used() -> None:
    sleeps: list[float] = []
    client = _client([_rate_limit("try again in 20s"), llm_response("ok")], sleeps)

    response = client.complete(messages=[], tools=[])

    assert sleeps == [20.0]
    assert response.attempts[0].retry_after_seconds == 20.0
    assert response.attempts[0].delay_seconds == 20.0


def test_backoff_used_when_hint_is_smaller() -> None:
    sleeps: list[float] = []
    client = _client([_rate_limit("try again in 1s"), llm_response("ok")], sleeps)

    client.complete(messages=[], tools=[])

    assert sleeps == [3.0]


def test_no_hint_keeps_plain_backoff() -> None:
    sleeps: list[float] = []
    client = _client([_rate_limit(), _rate_limit(), llm_response("ok")], sleeps)

    client.complete(messages=[], tools=[])

    assert sleeps == [3.0, 6.0]


def test_hint_over_max_fails_fast_without_sleeping() -> None:
    sleeps: list[float] = []
    client = _client(
        [_rate_limit("try again in 300s"), llm_response("ok")],
        sleeps,
        max_retry_after_seconds=60.0,
    )

    with pytest.raises(LLMCallFailed) as info:
        client.complete(messages=[], tools=[])

    assert sleeps == []
    assert "exceeds" in str(info.value)
    assert info.value.attempt_log[0].retry_after_seconds == 300.0


def test_permanent_error_ignores_hint() -> None:
    sleeps: list[float] = []
    bad = openai.BadRequestError(
        "try again in 5s",
        response=httpx.Response(400, request=_REQ),
        body=None,
    )
    client = _client([bad, llm_response("ok")], sleeps)

    with pytest.raises(LLMCallFailed) as info:
        client.complete(messages=[], tools=[])

    assert sleeps == []
    assert info.value.attempt_log[0].retry_after_seconds is None


def test_attempt_log_reaches_trace() -> None:
    sink = InMemorySink()
    client = _client([_rate_limit("try again in 4s"), llm_response("ok")], [])
    registry = ToolRegistry()
    registry.register(ListFilesTool(Workspace(Path.cwd())))
    agent = AgentLoop(
        client=client, registry=registry,
        executor=ToolExecutor(registry), trace=sink,
    )

    state = agent.run("go")

    assert state.status == AgentStatus.COMPLETED
    llm = next(e for e in sink.events if e.type == "llm_call")
    log = llm.data["attempt_log"]
    assert log[0]["kind"] == "transient"
    assert log[0]["retry_after_s"] == 4.0
    assert llm.data["attempts"] == 2
