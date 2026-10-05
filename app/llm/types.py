from __future__ import annotations

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

    def __add__(self, other: Usage) -> Usage:
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

