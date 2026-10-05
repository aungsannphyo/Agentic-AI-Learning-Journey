from pathlib import Path
from types import SimpleNamespace

from app.llm.openai_client import OpenAIClient
from app.llm.types import user_message
from app.tools import ListFilesTool, Workspace
from tests.builders import SdkItem


class FakeSDK:
    def __init__(self, response) -> None:
        self._response = response
        self.calls: list[dict] = []
        self.responses = SimpleNamespace(create=self._create)

    def _create(self, **kwargs):
        self.calls.append(kwargs)
        return self._response


def _fn_call(call_id: str, name: str, arguments: str) -> SdkItem:
    return SdkItem(
        type="function_call", call_id=call_id, name=name, arguments=arguments
    )


def _client(response, **kw) -> tuple[OpenAIClient, FakeSDK]:
    sdk = FakeSDK(response)
    return (
        OpenAIClient(
            sdk_client=sdk,
            model="test-model",
            temperature=0.0,
            system_prompt="sys",
            **kw,
        ),
        sdk,
    )


def _tools():
    return [ListFilesTool(Workspace(Path.cwd()))]


def test_function_call_is_parsed_into_tool_call() -> None:
    resp = SimpleNamespace(
        output=[_fn_call("c1", "list_files", '{"path": "app"}')],
        output_text="",
        usage=None,
    )
    client, _ = _client(resp)

    r = client.complete(
        messages=[user_message("hi")], tools=_tools()
    )

    calls = r.tool_calls
    assert len(calls) == 1
    assert calls[0].call_id == "c1"
    assert calls[0].tool_name == "list_files"
    assert calls[0].arguments == {"path": "app"}
    assert calls[0].parse_error is None


def test_final_text_has_no_tool_calls() -> None:
    resp = SimpleNamespace(
        output=[SdkItem(type="message")], output_text="done", usage=None
    )
    client, _ = _client(resp)

    r = client.complete(messages=[], tools=_tools())

    assert r.tool_calls == ()


def test_malformed_arguments_become_parse_error_not_exception() -> None:
    resp = SimpleNamespace(
        output=[_fn_call("c1", "list_files", "{bad")], output_text="", usage=None
    )
    client, _ = _client(resp)

    r = client.complete(messages=[], tools=_tools())

    assert r.tool_calls[0].parse_error is not None
    assert r.tool_calls[0].arguments == {}


def test_request_shape_sent_to_sdk() -> None:
    resp = SimpleNamespace(output=[], output_text="x", usage=None)
    client, sdk = _client(resp)
    messages = [user_message("hi")]

    client.complete(messages=messages, tools=_tools())

    sent = sdk.calls[0]
    assert sent["model"] == "test-model"
    assert sent["instructions"] == "sys"
    assert sent["input"] == [{"role": "user", "content": "hi"}]
    assert sent["temperature"] == 0.0
    assert sent["tools"][0]["name"] == "list_files"
    assert sent["tools"][0]["strict"] is True


def test_non_function_items_are_ignored() -> None:
    resp = SimpleNamespace(
        output=[
            SdkItem(type="reasoning"),
            _fn_call("c1", "list_files", "{}"),
        ],
        output_text="",
        usage=None,
    )
    client, _ = _client(resp)

    r = client.complete(messages=[], tools=_tools())

    assert [c.call_id for c in r.tool_calls] == ["c1"]
