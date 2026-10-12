from app.agent.history import ExecutionRecord
from app.agent.nudges import no_progress_nudge, trailing_empty_searches


def _s(query: str, hits: int = 0, ok: bool = True) -> ExecutionRecord:
    return ExecutionRecord(
        "search_text",
        {"query": query},
        ok,
        [{}] * hits if ok else None,
        None if ok else "x",
        1.0,
    )


def _r(ok: bool = True) -> ExecutionRecord:
    return ExecutionRecord("read_file", {"path": "a"}, ok, {}, None, 1.0)


def _l() -> ExecutionRecord:
    return ExecutionRecord("list_files", {"path": ""}, True, [], None, 1.0)


def test_counts_consecutive_empty_searches() -> None:
    assert trailing_empty_searches([_s("a"), _s("b")]) == ["a", "b"]


def test_search_with_hits_resets() -> None:
    assert trailing_empty_searches([_s("a"), _s("b", hits=2), _s("c")]) == ["c"]


def test_successful_read_resets() -> None:
    assert trailing_empty_searches([_s("a"), _s("b"), _r()]) == []


def test_list_files_is_transparent() -> None:
    assert trailing_empty_searches([_s("a"), _l(), _s("b")]) == ["a", "b"]


def test_failed_search_is_ignored_not_counted() -> None:
    assert trailing_empty_searches([_s("a"), _s("b", ok=False)]) == ["a"]


def test_nudge_below_threshold_is_none() -> None:
    assert no_progress_nudge([_s("a"), _s("b")], threshold=3) is None


def test_nudge_names_queries_and_allows_absence() -> None:
    note = no_progress_nudge([_s("smtp"), _s("mail"), _s("email")], threshold=3)
    assert note is not None
    assert '"smtp"' in note and "does not contain" in note
