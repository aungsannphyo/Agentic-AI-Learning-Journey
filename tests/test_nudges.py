from app.agent.history import ExecutionRecord
from app.agent.nudges import failure_nudge, trailing_failures


def _rec(ok: bool, tool: str = "read_file", error: str | None = None) -> ExecutionRecord:
    return ExecutionRecord(
        tool_name=tool,
        arguments={},
        success=ok,
        result=None,
        error=None if ok else (error or "boom"),
        duration_ms=1.0,
    )


def test_no_nudge_below_threshold() -> None:
    assert failure_nudge([_rec(False)], threshold=2) is None


def test_nudge_after_two_consecutive_failures() -> None:
    note = failure_nudge([_rec(False, error="File not found: a"), _rec(False)])
    assert note is not None
    assert "last 2 tool calls failed" in note
    assert "list_files" in note


def test_success_resets_trailing_failures() -> None:
    records = [_rec(False), _rec(False), _rec(True)]
    assert trailing_failures(records) == []
    assert failure_nudge(records) is None


def test_failures_before_a_success_do_not_count() -> None:
    records = [_rec(False), _rec(True), _rec(False)]
    assert len(trailing_failures(records)) == 1


def test_nudge_does_not_suggest_concluding_absence() -> None:
    note = failure_nudge([_rec(False), _rec(False)])
    assert note is not None
    assert "not present" not in note and "conclude" not in note.lower()
