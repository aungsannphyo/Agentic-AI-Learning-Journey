# Agent Runtime — Test Fixtures & Doubles Snapshot (`tests/`)

Centralized test fixtures, test doubles (FakeClock, FakeSDK, ScriptedClient), and builders for deterministic tests without network or sleep.

**Files count**: 1 files | **Active status**: 151 tests passed, ruff/mypy clean

## ဖိုင်များ မာတိကာ (Table of Contents)

- [`tests/builders.py`](#testsbuilderspy)

---

### `tests/builders.py` <a id="testsbuilderspy"></a>

```python
import json
from types import SimpleNamespace
from typing import Any

from app.llm import FakeResponse, LLMResponse, extract_usage


class SdkItem:
    """Fake SDK output item that serializes like a pydantic object."""

    def __init__(self, **data) -> None:
        self._data = data
        for k, v in data.items():
            setattr(self, k, v)

    def model_dump(self, **_kw):
        return dict(self._data)


def llm_response(text: str = "ok") -> LLMResponse:
    return LLMResponse(text=text, tool_calls=(), usage=None)


def tool_outputs(messages: list[dict]) -> list[dict]:
    """Parsed outputs of all tool_result messages."""
    return [
        json.loads(m["output"])
        for m in messages
        if m.get("kind") == "tool_result"
    ]


def usage(i: int = 1, o: int = 1) -> SimpleNamespace:
    return SimpleNamespace(input_tokens=i, output_tokens=o)


def tool_call_response(
    call_id: str, name: str, arguments: dict[str, Any] | str
) -> FakeResponse:
    raw = arguments if isinstance(arguments, str) else json.dumps(arguments)
    return FakeResponse(
        output_text="",
        output=[
            SimpleNamespace(
                type="function_call", call_id=call_id, name=name, arguments=raw
            )
        ],
        usage=usage(),
    )


def final_response(text: str = "done") -> FakeResponse:
    return FakeResponse(output_text=text, output=[], usage=usage())


def function_call_item(
    *,
    call_id: str,
    name: str,
    arguments: str,
) -> SimpleNamespace:
    """Build a fake LLM output item that looks like a function_call."""
    return SimpleNamespace(
        type="function_call",
        call_id=call_id,
        name=name,
        arguments=arguments,
    )


class FakeClock:
    """Manually-advanced clock for deterministic tests without sleep()."""

    def __init__(self, value: float = 0.0) -> None:
        self.value = value

    def now(self) -> float:
        return self.value


class FakeSDK:
    """Fake provider SDK for testing OpenAIClient complete()."""

    def __init__(self, response: Any) -> None:
        self._response = response
        self.calls: list[dict[str, Any]] = []
        self.responses = SimpleNamespace(create=self._create)

    def _create(self, **kwargs: Any) -> Any:
        self.calls.append(kwargs)
        return self._response


class ScriptedClient:
    """Raises or returns items from a preconfigured script, one per call."""

    def __init__(self, script: list[Any]) -> None:
        self._script = list(script)
        self.calls = 0

    def complete(self, *, messages: Any, tools: Any, should_abort: Any = None) -> Any:
        self.calls += 1
        item = self._script.pop(0)
        if isinstance(item, Exception):
            raise item
        if isinstance(item, FakeResponse):
            return LLMResponse(
                text=item.output_text,
                tool_calls=(),
                usage=extract_usage(item),
            )
        return item
```

---
