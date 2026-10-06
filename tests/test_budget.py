import pytest

from app.agent.budget import (
    BudgetTracker,
    RuntimeBudget,
)
from tests.builders import FakeClock


def test_budget_is_not_expired() -> None:
    clock = FakeClock()

    tracker = BudgetTracker(
        budget=RuntimeBudget(
            max_wall_time_seconds=10.0
        ),
        clock=clock,
    )

    clock.value = 5.0

    assert tracker.is_expired() is False


def test_budget_expires() -> None:
    clock = FakeClock()

    tracker = BudgetTracker(
        budget=RuntimeBudget(
            max_wall_time_seconds=10.0
        ),
        clock=clock,
    )

    clock.value = 10.0

    assert tracker.is_expired() is True


def test_invalid_budget_is_rejected() -> None:
    with pytest.raises(ValueError):
        RuntimeBudget(
            max_wall_time_seconds=0
        )
