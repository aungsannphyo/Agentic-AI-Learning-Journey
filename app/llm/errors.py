from __future__ import annotations

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
