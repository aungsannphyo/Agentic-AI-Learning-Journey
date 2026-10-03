import pytest

from app.agent.loop_guard import LoopGuard, call_fingerprint


def test_repetition_is_detected() -> None:
    guard = LoopGuard(
        max_repeated_calls=3
    )

    assert guard.record("read_file:a.py") is False
    assert guard.record("read_file:a.py") is False
    assert guard.record("read_file:a.py") is True


def test_different_calls_are_independent() -> None:
    guard = LoopGuard(
        max_repeated_calls=2
    )

    assert guard.record("read_file:a.py") is False
    assert guard.record("read_file:b.py") is False

    assert guard.record("read_file:a.py") is True


def test_invalid_limit_is_rejected() -> None:
    with pytest.raises(ValueError):
        LoopGuard(max_repeated_calls=0)


def test_fingerprint_normalizes_argument_order() -> None:
    first = call_fingerprint(
        "read_file",
        {
            "path": "app/main.py",
            "max_bytes": 1000,
        },
    )

    second = call_fingerprint(
        "read_file",
        {
            "max_bytes": 1000,
            "path": "app/main.py",
        },
    )

    assert first == second
