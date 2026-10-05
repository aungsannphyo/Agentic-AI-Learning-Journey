from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from app.tools import Tool, ToolCall

from .llm_errors import classify_llm_error
from .retry import ErrorKind, RetryPolicy


class LLMCallFailed(Exception):
    """Raised when an LLM call fails permanently or exhausts retries."""

    def __init__(self, message: str, *, attempts: int, kind: ErrorKind) -> None:
        super().__init__(message)
        self.attempts = attempts
        self.kind = kind


class DeadlineExceeded(Exception):
    """Raised when the run deadline expires while waiting to retry."""


@dataclass(frozen=True)
class AttemptRecord:
    attempt: int
    error: str
    kind: ErrorKind
    delay_seconds: float


class ResilientClient:
    """
    Retry decorator around any ToolCallingClient.

    Only the LLM call is retried. Tool execution is NOT retried here:
    tools may have side effects; their failures go back to the model.
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
        self._deadline_expired: Callable[[], bool] | None = None
        self._classify = classify
        self.attempt_log: list[AttemptRecord] = []

    def set_deadline_check(self, check: Callable[[], bool] | None) -> None:
        """Bind the current run's deadline. Called by AgentLoop at run start."""
        self._deadline_expired = check
        self.attempt_log = []

    def respond_with_tools(
        self,
        *,
        conversation: list[dict[str, Any]],
        tools: list[Tool],
    ) -> tuple[Any, list[ToolCall]]:
        attempt = 1
        while True:
            try:
                return self._inner.respond_with_tools(
                    conversation=conversation, tools=tools
                )
            except Exception as exc:  # noqa: BLE001 - classified below
                kind = self._classify(exc)
                decision = self._policy.decide(
                    attempt=attempt, error_kind=kind)

                self.attempt_log.append(
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
                    ) from exc

                if self._deadline_expired is not None and self._deadline_expired():
                    raise DeadlineExceeded(
                        "run deadline expired while retrying LLM call"
                    ) from exc

                self._sleep(decision.delay_seconds)
                attempt += 1
