import pytest

from app.agent.retry import (
    ErrorKind,
    RetryPolicy,
)


def test_permanent_error_is_not_retried() -> None:
    policy = RetryPolicy(
        max_attempts=3,
        base_delay_seconds=0.5,
    )

    decision = policy.decide(
        attempt=1,
        error_kind=ErrorKind.PERMANENT,
    )

    assert decision.should_retry is False
    assert decision.delay_seconds == 0.0
    assert decision.reason == "permanent error"


def test_transient_error_is_retried() -> None:
    policy = RetryPolicy(
        max_attempts=3,
        base_delay_seconds=0.5,
    )

    decision = policy.decide(
        attempt=1,
        error_kind=ErrorKind.TRANSIENT,
    )

    assert decision.should_retry is True
    assert decision.delay_seconds == 0.5


def test_exponential_backoff() -> None:
    policy = RetryPolicy(
        max_attempts=5,
        base_delay_seconds=0.5,
    )

    first = policy.decide(
        attempt=1,
        error_kind=ErrorKind.TRANSIENT,
    )

    second = policy.decide(
        attempt=2,
        error_kind=ErrorKind.TRANSIENT,
    )

    third = policy.decide(
        attempt=3,
        error_kind=ErrorKind.TRANSIENT,
    )

    assert first.delay_seconds == 0.5
    assert second.delay_seconds == 1.0
    assert third.delay_seconds == 2.0


def test_backoff_is_capped() -> None:
    policy = RetryPolicy(
        max_attempts=10,
        base_delay_seconds=1.0,
        max_delay_seconds=3.0,
    )

    decision = policy.decide(
        attempt=5,
        error_kind=ErrorKind.TRANSIENT,
    )

    assert decision.delay_seconds == 3.0


def test_retry_stops_after_budget() -> None:
    policy = RetryPolicy(
        max_attempts=3,
        base_delay_seconds=0.5,
    )

    decision = policy.decide(
        attempt=3,
        error_kind=ErrorKind.TRANSIENT,
    )

    assert decision.should_retry is False
    assert decision.delay_seconds == 0.0
    assert decision.reason == "retry budget exhausted"


def test_invalid_attempt_is_rejected() -> None:
    policy = RetryPolicy()

    with pytest.raises(ValueError):
        policy.decide(
            attempt=0,
            error_kind=ErrorKind.TRANSIENT,
        )


def test_invalid_max_attempts_is_rejected() -> None:
    with pytest.raises(ValueError):
        RetryPolicy(max_attempts=0)
