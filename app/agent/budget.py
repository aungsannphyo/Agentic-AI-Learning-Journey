from dataclasses import dataclass

from .clock import Clock


@dataclass(frozen=True)
class RuntimeBudget:
    max_iterations: int = 10
    max_wall_time_seconds: float = 60.0
    per_call_timeout_seconds: float = 30.0

    def __post_init__(self) -> None:
        if self.max_iterations < 1:
            raise ValueError(
                "max_iterations must be >= 1"
            )

        if self.max_wall_time_seconds <= 0:
            raise ValueError(
                "max_wall_time_seconds must be > 0"
            )

        if self.per_call_timeout_seconds <= 0:
            raise ValueError(
                "per_call_timeout_seconds must be > 0"
            )


class BudgetTracker:
    def __init__(
        self,
        budget: RuntimeBudget,
        clock: Clock,
    ) -> None:
        self._budget = budget
        self._clock = clock
        self._started_at = clock.now()

    def elapsed_seconds(self) -> float:
        return (
            self._clock.now()
            - self._started_at
        )

    def is_expired(self) -> bool:
        return (
            self.elapsed_seconds()
            >= self._budget.max_wall_time_seconds
        )
