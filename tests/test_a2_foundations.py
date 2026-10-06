import json
from pathlib import Path
from types import SimpleNamespace

import httpx
import openai
import pytest

from app.llm import (
    DeadlineExceeded,
    FakeLLMClient,
    LLMCallFailed,
    OpenAIClient,
    ResilientClient,
    RetryPolicy,
)
from app.llm.types import (
    LLMResponse,
    assistant_message,
    tool_result_message,
    user_message,
)
from app.tools import ListFilesTool, Workspace
from tests.builders import FakeSDK as _FakeSDK
from tests.builders import SdkItem, final_response, tool_call_response


def _tools():
    return [ListFilesTool(Workspace(Path.cwd()))]


def test_neutral_conversion_roundtrip_to_openai_input() -> None:
    items = [{"type": "function_call", "call_id": "c1", "name": "x", "arguments": "{}"}]
    resp = LLMResponse(text="", tool_calls=(), usage=None, assistant_items=tuple(items))
    messages = [
        user_message("hi"),
        assistant_message(resp),
        tool_result_message("c1", '{"success": true}'),
    ]

    out = OpenAIClient._to_openai_input(messages)

    assert out[0] == {"role": "user", "content": "hi"}
    assert out[1] == items[0]
    assert out[2] == {
        "type": "function_call_output",
        "call_id": "c1",
        "output": '{"success": true}',
    }


def test_messages_are_json_serializable() -> None:
    resp = LLMResponse(
        text="",
        tool_calls=(),
        usage=None,
        assistant_items=({"type": "reasoning", "id": "r1"},),
    )
    messages = [user_message("hi"), assistant_message(resp), tool_result_message("c", "o")]

    json.dumps(messages)  # must not raise


def test_complete_returns_llm_response_with_serializable_items() -> None:
    sdk_resp = SimpleNamespace(
        output=[
            SdkItem(type="reasoning", id="r1"),
            SdkItem(type="function_call", call_id="c1", name="list_files", arguments='{"path": ""}'),
        ],
        output_text="",
        usage=SimpleNamespace(input_tokens=3, output_tokens=2),
    )
    client = OpenAIClient(
        sdk_client=_FakeSDK(sdk_resp), model="m", temperature=0.0, system_prompt="s"
    )

    result = client.complete(messages=[user_message("hi")], tools=_tools())

    assert isinstance(result, LLMResponse)
    assert [c.call_id for c in result.tool_calls] == ["c1"]
    assert result.usage is not None and result.usage.total_tokens == 5
    json.dumps(list(result.assistant_items))  # serializable
    assert result.assistant_items[0]["type"] == "reasoning"


def test_complete_sends_converted_input_to_sdk() -> None:
    sdk = _FakeSDK(SimpleNamespace(output=[], output_text="x", usage=None))
    client = OpenAIClient(sdk_client=sdk, model="m", temperature=0.0, system_prompt="s")

    client.complete(messages=[user_message("hello")], tools=_tools())

    assert sdk.calls[0]["input"] == [{"role": "user", "content": "hello"}]


def test_unserializable_provider_item_fails_loudly() -> None:
    sdk_resp = SimpleNamespace(output=[object()], output_text="", usage=None)
    client = OpenAIClient(sdk_client=_FakeSDK(sdk_resp), model="m", temperature=0.0)

    with pytest.raises((TypeError, AttributeError)):
        client.complete(messages=[user_message("hi")], tools=_tools())


def test_fake_client_complete_follows_sequence() -> None:
    fake = FakeLLMClient(
        response="x",
        response_sequence=[
            tool_call_response("c1", "list_files", {"path": "."}),
            final_response("done"),
        ],
    )

    first = fake.complete(messages=[user_message("go")], tools=_tools())
    second = fake.complete(messages=[user_message("go")], tools=_tools())

    assert first.tool_calls[0].tool_name == "list_files"
    assert second.text == "done" and second.tool_calls == ()
    assert first.usage is not None


def test_resilient_complete_is_stateless_across_calls() -> None:
    class Flaky:
        def __init__(self) -> None:
            self.n = 0

        def complete(self, *, messages, tools):
            self.n += 1
            if self.n == 1:
                raise ConnectionError("boom")  # unknown -> permanent
            return LLMResponse(text="ok", tool_calls=(), usage=None)

    client = ResilientClient(Flaky(), RetryPolicy(), sleep=lambda _s: None)

    with pytest.raises(LLMCallFailed):
        client.complete(messages=[], tools=[])

    response = client.complete(messages=[], tools=[])
    assert response.text == "ok"
    assert response.attempts == ()  # nothing carried over from the failed call


def test_resilient_complete_deadline_is_a_parameter() -> None:
    req = httpx.Request("POST", "https://example.invalid")

    class Timeouts:
        def complete(self, *, messages, tools):
            raise openai.APITimeoutError(request=req)

    client = ResilientClient(Timeouts(), RetryPolicy(max_attempts=3), sleep=lambda _s: None)

    with pytest.raises(DeadlineExceeded):
        client.complete(messages=[], tools=[], should_abort=lambda: True)
