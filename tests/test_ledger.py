import pytest

from app.agent.history import ExecutionRecord
from app.agent.ledger import build_ledger


def _rec(
    tool: str,
    args: dict,
    *,
    ok: bool = True,
    result=None,
    error: str | None = None,
) -> ExecutionRecord:
    return ExecutionRecord(
        tool_name=tool,
        arguments=args,
        success=ok,
        result=result,
        error=error,
        duration_ms=1.0,
    )


def test_empty_history_returns_none() -> None:
    assert build_ledger([]) is None


def test_lists_files_read_deduplicated_and_in_order() -> None:
    note = build_ledger([
        _rec("read_file", {"path": "src/a.py"}),
        _rec("read_file", {"path": "src/b.py"}),
        _rec("read_file", {"path": "src/a.py"}),
    ])
    assert note is not None
    assert "Files read: src/a.py, src/b.py" in note


def test_failed_read_is_not_counted_as_read() -> None:
    note = build_ledger([
        _rec("read_file", {"path": "nope.py"}, ok=False, error="File not found: nope.py"),
    ])
    assert note is not None
    assert "Files read" not in note
    assert "Failed calls: read_file(nope.py): File not found" in note


def test_search_shows_query_and_match_count() -> None:
    note = build_ledger([
        _rec("search_text", {"query": "tax"}, result=[{"line": 1}, {"line": 2}]),
        _rec("search_text", {"query": "smtp"}, result=[]),
    ])
    assert note is not None
    assert '"tax" (2 matches)' in note
    assert '"smtp" (0 matches)' in note


def test_sections_are_capped() -> None:
    records = [_rec("read_file", {"path": f"f{i}.py"}) for i in range(8)]
    note = build_ledger(records)
    assert note is not None
    assert "(+3 more)" in note
    assert "f7.py" not in note


def test_long_error_and_args_are_clipped() -> None:
    note = build_ledger([
        _rec("read_file", {"path": "p" * 200}, ok=False, error="e" * 500),
    ])
    assert note is not None
    assert len(note) < 400


def test_only_list_files_returns_none() -> None:
    """list_files is not tracked — ledger stays empty."""
    note = build_ledger([
        _rec("list_files", {"path": "src"}, result=["a.py", "b.py"]),
    ])
    assert note is None


def test_mixed_tools_correct_sections() -> None:
    note = build_ledger([
        _rec("read_file", {"path": "app.py"}),
        _rec("search_text", {"query": "config"}, result=[{"line": 3}]),
        _rec("list_files", {"path": ""}, result=["app.py"]),
        _rec("read_file", {"path": "bad.py"}, ok=False, error="Not found"),
    ])
    assert note is not None
    assert "Files read: app.py" in note
    assert '"config" (1 matches)' in note
    assert "Failed calls: read_file(bad.py): Not found" in note
    # list_files should not appear anywhere
    assert "list_files" not in note.split("Failed")[0]


@pytest.mark.parametrize("result", [None, "string", 42])
def test_search_non_list_result_counts_zero(result) -> None:
    note = build_ledger([
        _rec("search_text", {"query": "x"}, result=result),
    ])
    assert note is not None
    assert '"x" (0 matches)' in note
