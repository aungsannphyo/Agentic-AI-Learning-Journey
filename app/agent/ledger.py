"""Evidence ledger: objective, code-derived facts about what the agent has
actually done. Built from ExecutionHistory, never from model claims.

Pure functions over ExecutionRecord so it is trivially testable and has no
provider or loop knowledge.
"""

from collections.abc import Sequence

from .history import ExecutionRecord

_MAX_PER_SECTION = 5
_MAX_ERROR_CHARS = 80
_MAX_ARG_CHARS = 40


def _clip(text: str, limit: int) -> str:
    one_line = " ".join(text.split())
    return one_line if len(one_line) <= limit else one_line[: limit - 3] + "..."


def _capped(items: list[str]) -> str:
    shown = items[:_MAX_PER_SECTION]
    extra = len(items) - len(shown)
    text = ", ".join(shown)
    return f"{text} (+{extra} more)" if extra > 0 else text


def _search_label(record: ExecutionRecord) -> str:
    query = _clip(str(record.arguments.get("query", "")), _MAX_ARG_CHARS)
    count = len(record.result) if isinstance(record.result, list) else 0
    return f'"{query}" ({count} matches)'


def _failure_label(record: ExecutionRecord) -> str:
    args = _clip(
        ", ".join(f"{v}" for v in record.arguments.values()), _MAX_ARG_CHARS
    )
    error = _clip(record.error or "unknown error", _MAX_ERROR_CHARS)
    return f"{record.tool_name}({args}): {error}"


def build_ledger(records: Sequence[ExecutionRecord]) -> str | None:
    """Return a short progress note, or None when there is nothing to report."""
    files: list[str] = []
    searches: list[str] = []
    failures: list[str] = []

    for record in records:
        if not record.success:
            failures.append(_failure_label(record))
        elif record.tool_name == "read_file":
            path = str(record.arguments.get("path", ""))
            if path and path not in files:
                files.append(path)
        elif record.tool_name == "search_text":
            searches.append(_search_label(record))

    lines: list[str] = []
    if files:
        lines.append(f"- Files read: {_capped(files)}")
    if searches:
        lines.append(f"- Searches done: {_capped(searches)}")
    if failures:
        lines.append(f"- Failed calls: {_capped(failures)}")
    if not lines:
        return None

    return (
        "System note (not from the user). Progress so far, from your actual "
        "tool calls:\n" + "\n".join(lines)
    )
