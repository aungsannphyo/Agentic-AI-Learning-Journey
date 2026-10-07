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
