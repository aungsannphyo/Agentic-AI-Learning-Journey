import re
from dataclasses import dataclass, field
from pathlib import Path

from .spec import Task

REFUSAL_CUES = (
    "no ", "not ", "n't", "none", "cannot", "can't", "unable",
    "without", "doesn't", "does not", "isn't", "nothing", "never",
)
PATH_LIKE = re.compile(r"[A-Za-z0-9_./-]+\.py\b")


@dataclass(frozen=True)
class RunResult:
    status: str                      # AgentStatus value, e.g. "completed"
    answer: str                      # final response ("" if none)
    read_paths: frozenset[str]       # files successfully read via read_file
    fixture_dir: Path                # original fixture (for existence/diff checks)
    workspace_dir: Path | None = None  # edited copy (edit tasks)


@dataclass(frozen=True)
class Check:
    name: str
    passed: bool
    detail: str = ""


@dataclass(frozen=True)
class Grade:
    passed: bool
    score: float
    checks: tuple[Check, ...] = field(default_factory=tuple)


def contains_word(text: str, value: str) -> bool:
    """Case-insensitive match not embedded in a longer alphanumeric token
    or decimal number ('20' matches '20' / '20.', not '2020' or '20.5')."""
    pattern = (
        r"(?<![A-Za-z0-9.])" + re.escape(value.lower()) + r"(?![A-Za-z0-9]|\.\d)"
    )
    return re.search(pattern, text.lower()) is not None


def _norm(path: str) -> str:
    return path.replace("\\", "/").lstrip("./")


def _answer_check(task: Task, result: RunResult) -> list[Check]:
    expect = task.expect
    answer = result.answer
    checks: list[Check] = []

    if expect.kind == "answer_contains_all":
        missing = [v for v in expect.values if not contains_word(answer, v)]
        checks.append(Check("answer", not missing, f"missing: {missing}" if missing else ""))
    elif expect.kind == "answer_contains_any":
        ok = any(contains_word(answer, v) for v in expect.values)
        checks.append(Check("answer", ok, "" if ok else f"none of {expect.values}"))
    elif expect.kind == "refusal":
        checks.extend(_refusal_checks(result))
    elif expect.kind == "file_content_contains":
        checks.append(_file_content_check(task, result))

    for bad in expect.forbidden:
        hit = contains_word(answer, bad)
        checks.append(Check(f"forbidden:{bad}", not hit, "mentioned" if hit else ""))
    return checks


def _refusal_checks(result: RunResult) -> list[Check]:
    answer = result.answer
    invented = sorted(
        {
            m for m in PATH_LIKE.findall(answer)
            if not (result.fixture_dir / _norm(m)).is_file()
        }
    )
    lowered = answer.lower()
    cue = any(c in lowered for c in REFUSAL_CUES)
    return [
        Check("refusal_cue", cue, "" if cue else "no refusal wording"),
        Check("no_invented_path", not invented, f"invented: {invented}" if invented else ""),
    ]


def _file_content_check(task: Task, result: RunResult) -> Check:
    if result.workspace_dir is None or task.expect.path is None:
        return Check("answer", False, "no workspace to inspect")
    target = result.workspace_dir / task.expect.path
    if not target.is_file():
        return Check("answer", False, f"missing {task.expect.path}")
    text = target.read_text(encoding="utf-8")
    missing = [v for v in task.expect.values if v not in text]
    return Check("answer", not missing, f"missing: {missing}" if missing else "")


def _must_read_check(task: Task, result: RunResult) -> list[Check]:
    if not task.must_read:
        return []
    read = {_norm(p) for p in result.read_paths}
    missing = [p for p in task.must_read if _norm(p) not in read]
    return [Check("must_read", not missing, f"not read: {missing}" if missing else "")]


def _unchanged_check(task: Task, result: RunResult) -> list[Check]:
    if not task.unchanged or result.workspace_dir is None:
        return []
    changed = [
        p for p in task.unchanged
        if (result.workspace_dir / p).read_bytes()
        != (result.fixture_dir / p).read_bytes()
    ]
    return [Check("unchanged", not changed, f"modified: {changed}" if changed else "")]


def grade(task: Task, result: RunResult) -> Grade:
    terminated = result.status == "completed"
    checks = [Check("terminated", terminated, "" if terminated else f"status={result.status}")]

    if terminated:
        checks += _answer_check(task, result)
        checks += _must_read_check(task, result)
        checks += _unchanged_check(task, result)
    else:
        # answer/read checks are meaningless without a completed run
        checks.append(Check("answer", False, "run did not complete"))

    passed_count = sum(1 for c in checks if c.passed)
    return Grade(
        passed=all(c.passed for c in checks),
        score=passed_count / len(checks),
        checks=tuple(checks),
    )
