import json
from pathlib import Path

import httpx
import openai

from app.agent import AgentLoop, AgentStatus
from app.llm import FakeLLMClient, ResilientClient, RetryPolicy
from app.tools import ListFilesTool, ToolExecutor, ToolRegistry, Workspace

from tests.builders import final_response, llm_response, tool_call_response


def _loop(client) -> AgentLoop:
    registry = ToolRegistry()
    registry.register(ListFilesTool(Workspace(Path.cwd())))
    return AgentLoop(
        client=client, registry=registry, executor=ToolExecutor(registry)
    )


def test_conversation_is_json_serializable_after_a_run() -> None:
    fake = FakeLLMClient(
        response="x",
        response_sequence=[
            tool_call_response("c1", "list_files", {"path": "."}),
            final_response("done"),
        ],
    )

    state = _loop(fake).run("go")

    assert state.status == AgentStatus.COMPLETED
    json.dumps(state.conversation)  # must not raise


def test_retry_attempts_surface_on_state() -> None:
    req = httpx.Request("POST", "https://example.invalid")

    class Flaky:
        def __init__(self) -> None:
            self.n = 0

        def complete(self, *, messages, tools, should_abort=None):
            self.n += 1
            if self.n == 1:
                raise openai.APITimeoutError(request=req)
            return llm_response("ok")

    client = ResilientClient(Flaky(), RetryPolicy(max_attempts=3), sleep=lambda _s: None)

    state = _loop(client).run("go")

    assert state.status == AgentStatus.COMPLETED
    assert [a.kind.value for a in state.llm_attempts] == ["transient"]


def test_failed_call_attempts_surface_on_state() -> None:
    class Dies:
        def complete(self, *, messages, tools, should_abort=None):
            raise RuntimeError("nope")  # unknown -> permanent

    client = ResilientClient(Dies(), RetryPolicy(), sleep=lambda _s: None)

    state = _loop(client).run("go")

    assert state.status == AgentStatus.LLM_FAILED
    assert len(state.llm_attempts) == 1
