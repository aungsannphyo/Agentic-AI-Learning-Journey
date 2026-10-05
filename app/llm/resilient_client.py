from __future__ import annotations

import time
from collections.abc import Callable, Sequence
from dataclasses import replace
from typing import Any

from app.tools import Tool

from .errors import DeadlineExceeded, LLMCallFailed
from .llm_errors import classify_llm_error
from .retry import ErrorKind, RetryPolicy
from .types import AttemptRecord, LLMResponse


class ResilientClient:
    """Retry decorator around any LLMClient. Stateless.

    Only the LLM call is retried; tool execution never is (side effects).
    The attempt log travels on the response (or on the raised exception).
    """

    def __init__(
        self,
        inner: Any,
        policy: RetryPolicy,
        *,
        sleep: Callable[[float], None] = time.sleep,
        classify: Callable[[Exception], ErrorKind] = classify_llm_error,
    ) -> None:
        self._inner = inner
        self._policy = policy
        self._sleep = sleep
        self._classify = classify

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
            try:
                response = self._inner.complete(messages=messages, tools=tools)
                return replace(response, attempts=tuple(attempts))
            except Exception as exc:  # noqa: BLE001 - classified below
                kind = self._classify(exc)
                decision = self._policy.decide(attempt=attempt, error_kind=kind)
                attempts.append(
                    AttemptRecord(
                        attempt=attempt,
                        error=f"{type(exc).__name__}: {exc}",
                        kind=kind,
                        delay_seconds=decision.delay_seconds,
                    )
                )

                if not decision.should_retry:
                    raise LLMCallFailed(
                        f"LLM call failed ({decision.reason}) "
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

                self._sleep(decision.delay_seconds)
                attempt += 1
