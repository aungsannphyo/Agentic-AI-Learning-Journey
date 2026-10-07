# Agent Runtime — LLM Subsystem Layer Snapshot (`app/llm/`)

LLM client protocols, OpenAI/Groq client adapter, stateless resilient client, retry policies, error classifier, and provider-neutral message types.

**Files count**: 10 files | **Active status**: 151 tests passed, ruff/mypy clean

## ဖိုင်များ မာတိကာ (Table of Contents)

- [`app/llm/__init__.py`](#appllminitpy)
- [`app/llm/client.py`](#appllmclientpy)
- [`app/llm/errors.py`](#appllmerrorspy)
- [`app/llm/fake_client.py`](#appllmfakeclientpy)
- [`app/llm/llm_errors.py`](#appllmllmerrorspy)
- [`app/llm/openai_client.py`](#appllmopenaiclientpy)
- [`app/llm/openai_tools.py`](#appllmopenaitoolspy)
- [`app/llm/resilient_client.py`](#appllmresilientclientpy)
- [`app/llm/retry.py`](#appllmretrypy)
- [`app/llm/types.py`](#appllmtypespy)

---

### `app/llm/__init__.py` <a id="appllminitpy"></a>

```python
from .client import LLMClient
from .errors import DeadlineExceeded, LLMCallFailed
from .fake_client import FakeLLMClient, FakeResponse
from .llm_errors import classify_llm_error, retry_after_seconds
from .openai_client import OpenAIClient
from .openai_tools import to_openai_tool
from .resilient_client import ResilientClient
from .retry import ErrorKind, RetryDecision, RetryPolicy
from .types import AttemptRecord, LLMResponse, Usage, extract_usage

__all__ = [
    "AttemptRecord",
    "DeadlineExceeded",
    "ErrorKind",
    "FakeLLMClient",
    "FakeResponse",
    "LLMCallFailed",
    "LLMClient",
    "LLMResponse",
    "OpenAIClient",
    "ResilientClient",
    "RetryDecision",
    "RetryPolicy",
    "Usage",
    "classify_llm_error",
    "extract_usage",
    "retry_after_seconds",
    "to_openai_tool",
]
```

---

### `app/llm/client.py` <a id="appllmclientpy"></a>

```python
from collections.abc import Callable, Sequence
from typing import Any, Protocol

from app.tools import Tool

from .types import LLMResponse


class LLMClient(Protocol):
    """Provider-independent contract used by the agent loop.

    messages are provider-neutral (see app.llm.types message helpers).
    should_abort is consulted only by retry layers; plain provider
    clients accept and ignore it.
    """

    def complete(
        self,
        *,
        messages: list[dict[str, Any]],
        tools: Sequence[Tool],
        should_abort: Callable[[], bool] | None = None,
    ) -> LLMResponse:
        ...
```

---

### `app/llm/errors.py` <a id="appllmerrorspy"></a>

```python
from .retry import ErrorKind
from .types import AttemptRecord


class LLMCallFailed(Exception):
    """Raised when an LLM call fails permanently or exhausts retries."""

    def __init__(
        self,
        message: str,
        *,
        attempts: int,
        kind: ErrorKind,
        attempt_log: tuple[AttemptRecord, ...] = (),
    ) -> None:
        super().__init__(message)
        self.attempts = attempts
        self.kind = kind
        self.attempt_log = attempt_log


class DeadlineExceeded(Exception):
    """Raised when the run deadline expires while waiting to retry."""

    def __init__(
        self, message: str, *, attempt_log: tuple[AttemptRecord, ...] = ()
    ) -> None:
        super().__init__(message)
        self.attempt_log = attempt_log
```

---

### `app/llm/fake_client.py` <a id="appllmfakeclientpy"></a>

```python
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from typing import Any

from app.tools import parse_tool_call

from .types import LLMResponse, extract_usage


@dataclass
class FakeResponse:
    output_text: str
    output: list[Any] = field(default_factory=list)
    id: str = "fake-response-123"
    usage: Any = None


def _item_to_dict(item: Any) -> dict[str, Any]:
    if isinstance(item, dict):
        return item
    return {
        key: getattr(item, key)
        for key in ("type", "call_id", "name", "arguments")
        if hasattr(item, key)
    }


class FakeLLMClient:
    """Deterministic LLMClient for tests."""

    def __init__(
        self,
        response: str,
        *,
        response_sequence: list[FakeResponse] | None = None,
    ) -> None:
        self.response = response
        self._response_sequence: list[FakeResponse] = (
            list(response_sequence) if response_sequence else []
        )
        self.calls: list[dict[str, Any]] = []

    def complete(
        self,
        *,
        messages: list[dict[str, Any]],
        tools: Sequence[Any],
        should_abort: Callable[[], bool] | None = None,
    ) -> LLMResponse:
        self.calls.append(
            {
                "method": "complete",
                "messages": [dict(m) for m in messages],
                "tools": [t.name for t in tools],
            }
        )
        fake = (
            self._response_sequence.pop(0)
            if self._response_sequence
            else FakeResponse(output_text=self.response)
        )
        tool_calls = tuple(
            parse_tool_call(
                call_id=item.call_id,
                name=item.name,
                raw_arguments=item.arguments,
            )
            for item in fake.output
            if item.type == "function_call"
        )
        return LLMResponse(
            text=fake.output_text,
            tool_calls=tool_calls,
            usage=extract_usage(fake),
            assistant_items=tuple(_item_to_dict(i) for i in fake.output),
        )
```

---

### `app/llm/llm_errors.py` <a id="appllmllmerrorspy"></a>

```python
import re

import openai

from .retry import ErrorKind

_TRANSIENT: tuple[type[Exception], ...] = (
    openai.RateLimitError,
    openai.APITimeoutError,
    openai.APIConnectionError,
    openai.InternalServerError,
)

_HINT = re.compile(
    r"try again in\s+(\d+(?:\.\d+)?(?:ms|s|m)(?:\s*\d+(?:\.\d+)?(?:ms|s|m))*)",
    re.IGNORECASE,
)
_PART = re.compile(r"(\d+(?:\.\d+)?)(ms|s|m)")
_UNIT_SECONDS = {"ms": 0.001, "s": 1.0, "m": 60.0}


def classify_llm_error(error: Exception) -> ErrorKind:
    """
    Map an LLM-call exception to a retry classification.

    Unknown errors are PERMANENT: retrying something we do not
    understand is worse than failing loudly.

    NOTE: APITimeoutError subclasses APIConnectionError in the SDK;
    both are listed explicitly so intent survives a refactor.
    """
    if isinstance(error, _TRANSIENT):
        return ErrorKind.TRANSIENT
    return ErrorKind.PERMANENT


def _from_header(error: Exception) -> float | None:
    headers = getattr(getattr(error, "response", None), "headers", None)
    if headers is None:
        return None
    raw = headers.get("retry-after")
    if raw is None:
        return None
    try:
        value = float(raw)
    except (TypeError, ValueError):
        return None  # HTTP-date form is not supported
    return value if value >= 0 else None


def _from_message(error: Exception) -> float | None:
    match = _HINT.search(str(error))
    if match is None:
        return None
    parts = _PART.findall(match.group(1))
    if not parts:
        return None
    return sum(float(num) * _UNIT_SECONDS[unit] for num, unit in parts)


def retry_after_seconds(error: Exception) -> float | None:
    """Provider's own suggestion for how long to wait, if it gave one.

    Header first, then the "try again in 1m30.5s" phrase in the message.
    Returns None when neither is present or parseable.
    """
    header = _from_header(error)
    if header is not None:
        return header
    return _from_message(error)
```

---

### `app/llm/openai_client.py` <a id="appllmopenaiclientpy"></a>

```python
import os
from collections.abc import Callable, Sequence
from typing import Any

from openai import OpenAI

from app.tools import Tool, parse_tool_call

from .openai_tools import to_openai_tool
from .types import LLMResponse, extract_usage


def _function_calls(output: Sequence[Any]) -> list[Any]:
    """Provider output is untrusted; select by structural `type` tag.

    Typed as Any on purpose: the SDK union is wide and tests use
    duck-typed fakes, so narrowing by isinstance would couple both.
    """
    return [i for i in output if getattr(i, "type", None) == "function_call"]


class OpenAIClient:
    """OpenAI Responses API implementation of LLMClient (Groq-compatible)."""

    def __init__(
        self,
        *,
        model: str | None = None,
        temperature: float | None = None,
        system_prompt: str | None = None,
        timeout_seconds: float | None = None,
        sdk_client: Any | None = None,
    ) -> None:
        self._client: Any = sdk_client or OpenAI(
            api_key=os.environ["OPENAI_API_KEY"],
            base_url="https://api.groq.com/openai/v1",
            timeout=timeout_seconds,
            max_retries=0,
        )
        self._model: str = (model or os.getenv(
            "OPENAI_MODEL")) or "openai/gpt-oss-120b"
        self._temperature = (
            temperature
            if temperature is not None
            else float(os.getenv("OPENAI_TEMPERATURE", "0.2"))
        )
        self._system_prompt: str | None = system_prompt

    @staticmethod
    def _to_openai_input(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
        items: list[dict[str, Any]] = []
        for message in messages:
            kind = message["kind"]
            if kind == "user":
                items.append({"role": "user", "content": message["text"]})
            elif kind == "assistant":
                items.extend(message["items"])
            elif kind == "tool_result":
                items.append(
                    {
                        "type": "function_call_output",
                        "call_id": message["call_id"],
                        "output": message["output"],
                    }
                )
            else:
                raise ValueError(f"unknown message kind: {kind}")
        return items

    @staticmethod
    def _dump_item(item: Any) -> dict[str, Any]:
        if isinstance(item, dict):
            return item
        dump = getattr(item, "model_dump", None)
        if callable(dump):
            return dump(mode="json", exclude_none=True)
        raise TypeError(
            f"cannot serialize provider item of type {type(item).__name__}"
        )

    def complete(
        self,
        *,
        messages: list[dict[str, Any]],
        tools: Sequence[Tool],
        should_abort: Callable[[], bool] | None = None,
    ) -> LLMResponse:
        del should_abort
        response = self._client.responses.create(
            model=self._model,
            instructions=self._system_prompt,
            input=self._to_openai_input(messages),
            tools=[to_openai_tool(tool) for tool in tools],
            temperature=self._temperature,
        )

        tool_calls = tuple(
            parse_tool_call(
                call_id=item.call_id,
                name=item.name,
                raw_arguments=item.arguments,
            )
            for item in _function_calls(response.output)
        )

        return LLMResponse(
            text=response.output_text,
            tool_calls=tool_calls,
            usage=extract_usage(response),
            assistant_items=tuple(self._dump_item(i) for i in response.output),
        )
```

---

### `app/llm/openai_tools.py` <a id="appllmopenaitoolspy"></a>

```python
from typing import Any

from app.tools import Tool


def to_openai_tool(tool: Tool) -> dict[str, Any]:
    """Convert an internal Tool into an OpenAI function tool."""

    return {
        "type": "function",
        "name": tool.name,
        "description": tool.description,
        "parameters": tool.input_schema,
        "strict": True,
    }
```

---

### `app/llm/resilient_client.py` <a id="appllmresilientclientpy"></a>

```python
import time
from collections.abc import Callable, Sequence
from dataclasses import replace
from typing import Any

from app.tools import Tool

from .errors import DeadlineExceeded, LLMCallFailed
from .llm_errors import classify_llm_error, retry_after_seconds
from .retry import ErrorKind, RetryPolicy
from .types import AttemptRecord, LLMResponse


class ResilientClient:
    """Retry decorator around any LLMClient. Stateless.

    Only the LLM call is retried; tool execution never is (side effects).
    The attempt log travels on the response (or on the raised exception).
    A provider retry hint raises the wait to at least the hint; a hint
    longer than max_retry_after_seconds fails fast instead of waiting.
    """

    def __init__(
        self,
        inner: Any,
        policy: RetryPolicy,
        *,
        sleep: Callable[[float], None] = time.sleep,
        classify: Callable[[Exception], ErrorKind] = classify_llm_error,
        max_retry_after_seconds: float = 60.0,
    ) -> None:
        self._inner = inner
        self._policy = policy
        self._sleep = sleep
        self._classify = classify
        self._max_hint = max_retry_after_seconds

    def complete(
        self,
        *,
        messages: list[dict[str, Any]],
        tools: Sequence[Tool],
        should_abort: Callable[[], bool] | None = None,
    ) -> LLMResponse:
        attempts: list[AttemptRecord] = []
        attempt = 1
        while True:
            started = time.perf_counter()
            try:
                response = self._inner.complete(messages=messages, tools=tools)
                return replace(response, attempts=tuple(attempts))
            except Exception as exc:
                latency_ms = (time.perf_counter() - started) * 1000
                kind = self._classify(exc)
                decision = self._policy.decide(attempt=attempt, error_kind=kind)

                hint = (
                    retry_after_seconds(exc)
                    if kind == ErrorKind.TRANSIENT
                    else None
                )
                should_retry = decision.should_retry
                reason = decision.reason
                delay = decision.delay_seconds

                if should_retry and hint is not None:
                    if hint > self._max_hint:
                        should_retry = False
                        reason = (
                            f"retry-after {hint:.1f}s exceeds "
                            f"max wait {self._max_hint:.1f}s"
                        )
                    else:
                        delay = max(delay, hint)

                attempts.append(
                    AttemptRecord(
                        attempt=attempt,
                        error=f"{type(exc).__name__}: {exc}",
                        kind=kind,
                        delay_seconds=delay if should_retry else 0.0,
                        retry_after_seconds=hint,
                        latency_ms=latency_ms,
                    )
                )

                if not should_retry:
                    raise LLMCallFailed(
                        f"LLM call failed ({reason}) "
                        f"after {attempt} attempt(s): {exc}",
                        attempts=attempt,
                        kind=kind,
                        attempt_log=tuple(attempts),
                    ) from exc

                if should_abort is not None and should_abort():
                    raise DeadlineExceeded(
                        "run deadline expired while retrying LLM call",
                        attempt_log=tuple(attempts),
                    ) from exc

                self._sleep(delay)
                attempt += 1
```

---

### `app/llm/retry.py` <a id="appllmretrypy"></a>

```python
from dataclasses import dataclass
from enum import Enum


class ErrorKind(str, Enum):
    TRANSIENT = "transient"
    PERMANENT = "permanent"


@dataclass(frozen=True)
class RetryDecision:
    should_retry: bool
    delay_seconds: float
    reason: str


@dataclass(frozen=True)
class RetryPolicy:
    max_attempts: int = 3
    base_delay_seconds: float = 0.5
    max_delay_seconds: float = 8.0

    def __post_init__(self) -> None:
        if self.max_attempts < 1:
            raise ValueError("max_attempts must be >= 1")

        if self.base_delay_seconds < 0:
            raise ValueError(
                "base_delay_seconds must be >= 0"
            )

        if self.max_delay_seconds < 0:
            raise ValueError(
                "max_delay_seconds must be >= 0"
            )

    def classify(self, error_kind: ErrorKind) -> bool:
        return error_kind == ErrorKind.TRANSIENT

    def decide(
        self,
        *,
        attempt: int,
        error_kind: ErrorKind,
    ) -> RetryDecision:
        if attempt < 1:
            raise ValueError("attempt must be >= 1")

        if not self.classify(error_kind):
            return RetryDecision(
                should_retry=False,
                delay_seconds=0.0,
                reason="permanent error",
            )

        if attempt >= self.max_attempts:
            return RetryDecision(
                should_retry=False,
                delay_seconds=0.0,
                reason="retry budget exhausted",
            )

        delay = min(
            self.base_delay_seconds * (2 ** (attempt - 1)),
            self.max_delay_seconds,
        )

        return RetryDecision(
            should_retry=True,
            delay_seconds=delay,
            reason="transient error",
        )
```

---

### `app/llm/types.py` <a id="appllmtypespy"></a>

```python
from dataclasses import dataclass, field
from typing import Any

from app.tools import ToolCall

from .retry import ErrorKind


@dataclass(frozen=True)
class Usage:
    """Provider-independent token usage for one LLM call."""

    input_tokens: int = 0
    output_tokens: int = 0

    @property
    def total_tokens(self) -> int:
        return self.input_tokens + self.output_tokens

    def __add__(self, other: "Usage") -> "Usage":
        return Usage(
            input_tokens=self.input_tokens + other.input_tokens,
            output_tokens=self.output_tokens + other.output_tokens,
        )


def _first_int(obj: Any, *names: str) -> int | None:
    for name in names:
        value = getattr(obj, name, None)
        if isinstance(value, int) and not isinstance(value, bool):
            return value
    return None


def extract_usage(response: Any) -> Usage | None:
    """
    Normalise provider usage into Usage.

    Returns None (NOT zero) when the provider did not report usage.
    Silent zero would make budget enforcement fail open.

    Supports Responses-API naming (input_tokens/output_tokens) and
    Chat-Completions naming (prompt_tokens/completion_tokens).
    """
    raw = getattr(response, "usage", None)
    if raw is None:
        return None

    input_tokens = _first_int(raw, "input_tokens", "prompt_tokens")
    output_tokens = _first_int(raw, "output_tokens", "completion_tokens")

    if input_tokens is None or output_tokens is None:
        return None

    return Usage(input_tokens=input_tokens, output_tokens=output_tokens)


@dataclass(frozen=True)
class AttemptRecord:
    attempt: int
    error: str
    kind: ErrorKind
    delay_seconds: float
    retry_after_seconds: float | None = None
    latency_ms: float = 0.0


@dataclass(frozen=True)
class LLMResponse:
    """Provider-independent result of one LLM call.

    assistant_items are opaque, JSON-serializable provider items
    (message / function_call / reasoning ...) that the same provider
    must be given back on the next call. The loop stores them but
    never inspects them.
    """

    text: str
    tool_calls: tuple[ToolCall, ...]
    usage: Usage | None
    assistant_items: tuple[dict[str, Any], ...] = field(default_factory=tuple)
    attempts: tuple[AttemptRecord, ...] = field(default_factory=tuple)


# --- provider-neutral conversation messages -------------------------------
# Each message is a plain JSON-serializable dict with a "kind" key:
#   {"kind": "user", "text": str}
#   {"kind": "assistant", "items": [dict, ...]}      (opaque provider items)
#   {"kind": "tool_result", "call_id": str, "output": str}


def user_message(text: str) -> dict[str, Any]:
    return {"kind": "user", "text": text}


def assistant_message(response: LLMResponse) -> dict[str, Any]:
    return {"kind": "assistant", "items": list(response.assistant_items)}


def tool_result_message(call_id: str, output: str) -> dict[str, Any]:
    return {"kind": "tool_result", "call_id": call_id, "output": output}
```

---
