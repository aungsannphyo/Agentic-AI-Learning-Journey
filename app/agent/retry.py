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
