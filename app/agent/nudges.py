"""Code-triggered corrective nudges. Pure functions over ExecutionRecord:
no provider or loop knowledge. A nudge is advisory text appended as an
append-only user message (same mechanism as the evidence ledger).
"""

from collections.abc import Sequence

from .history import ExecutionRecord

_MAX_ERROR_CHARS = 100
_MAX_LISTED = 2


def _clip(text: str, limit: int) -> str:
    one_line = " ".join(text.split())
    return one_line if len(one_line) <= limit else one_line[: limit - 3] + "..."


def trailing_failures(records: Sequence[ExecutionRecord]) -> list[ExecutionRecord]:
    """Consecutive failed calls at the END of history (a success resets)."""
    tail: list[ExecutionRecord] = []
    for record in reversed(records):
        if record.success:
            break
        tail.append(record)
    tail.reverse()
    return tail


def failure_nudge(
    records: Sequence[ExecutionRecord], *, threshold: int = 2
) -> str | None:
    """Return a recovery note when the last `threshold`+ calls all failed."""
    tail = trailing_failures(records)
    if len(tail) < threshold:
        return None
    shown = tail[-_MAX_LISTED:]
    details = "; ".join(
        f"{r.tool_name}: {_clip(r.error or 'unknown error', _MAX_ERROR_CHARS)}"
        for r in shown
    )
    return (
        "System note (not from the user). Your last "
        f"{len(tail)} tool calls failed ({details}). "
        "Check paths with list_files before retrying the same call."
    )


EMPTY_ANSWER_NUDGE = (
    "System note (not from the user). Your last reply contained neither a "
    "tool call nor a final answer. Call a tool, or give your final answer."
)


def trailing_empty_searches(records: Sequence[ExecutionRecord]) -> list[str]:
    """Queries of consecutive empty successful searches at the END of history.

    read_file success resets (new information). list_files and failed calls
    are transparent: they neither extend nor reset the streak.
    """
    queries: list[str] = []
    for record in reversed(records):
        if record.tool_name == "read_file" and record.success:
            break
        if record.tool_name != "search_text" or not record.success:
            continue
        if isinstance(record.result, list) and len(record.result) == 0:
            queries.append(str(record.arguments.get("query", "")))
        else:
            break  # a search that found something resets
    queries.reverse()
    return queries


def no_progress_nudge(
    records: Sequence[ExecutionRecord], *, threshold: int = 3
) -> str | None:
    queries = trailing_empty_searches(records)
    if len(queries) < threshold:
        return None
    shown = ", ".join(f'"{_clip(q, 30)}"' for q in queries[-threshold:])
    return (
        "System note (not from the user). Your last "
        f"{len(queries)} searches returned no matches ({shown}). "
        "If the repository does not contain what the task asks about, "
        "say so clearly in your final answer instead of searching further."
    )

