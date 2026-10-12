import functools
import re
from dataclasses import dataclass, field
from pathlib import Path

from .spec import Task

REFUSAL_CUES = (
    "no ", "not ", "n't", "none", "cannot", "can't", "unable",
    "without", "doesn't", "does not", "isn't", "nothing", "never",
)
PATH_LIKE = re.compile(r"[A-Za-z0-9_./-]+\.py\b")
POINTER_VERBS = re.compile(
    r"\b(?:see|check|try|refer\s+to|look\s+at)\s+(?:the\s+)?([A-Za-z0-9_./-]+(?:\s+[A-Za-z0-9_.-]+)?)",
    re.IGNORECASE,
)
POINTER_STOP_WORDS = {
    "if", "whether", "that", "this", "it", "again", "out", "all",
    "each", "every", "any", "other", "another", "more", "further",
    "details", "here", "above", "below", "there", "to", "and",
}
POINTER_ENTITY_SUFFIXES = {
    "module", "service", "helper", "client", "file", "handler",
    "class", "function", "package", "component",
}


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
    or decimal number ('20' matches '20', '20.', '20.00'; not '2020' or '20.5')."""
    pattern = (
        r"(?<![A-Za-z0-9.])"
        + re.escape(value.lower())
        + r"(?![A-Za-z0-9])(?!\.\d*[1-9])"
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


def _is_real_path(fixture_dir: Path, path_str: str) -> bool:
    norm = _norm(path_str)
    if (fixture_dir / norm).is_file():
        return True
    if "/" not in norm and "\\" not in norm:
        return any(p.name == norm for p in fixture_dir.rglob("*.py"))
    return False


@functools.lru_cache(maxsize=16)
def _fixture_identifiers(fixture_dir: Path) -> frozenset[str]:
    identifiers: set[str] = set()
    for p in fixture_dir.rglob("*"):
        if p.is_file() and "__pycache__" not in p.parts:
            identifiers.add(p.name.lower())
            identifiers.add(p.stem.lower())
            try:
                rel = p.relative_to(fixture_dir).as_posix().lower()
                identifiers.add(rel)
            except ValueError:
                pass
            if p.suffix == ".py":
                try:
                    text = p.read_text(encoding="utf-8")
                    for token in re.findall(r"\b[A-Za-z_][A-Za-z0-9_]*\b", text):
                        identifiers.add(token.lower())
                except OSError:
                    pass
    return frozenset(identifiers)


def _is_real_entity(fixture_dir: Path, name: str) -> bool:
    norm = _norm(name).lower()
    if _is_real_path(fixture_dir, norm):
        return True
    return norm in _fixture_identifiers(fixture_dir)


def _find_invented_pointers(fixture_dir: Path, answer: str) -> list[str]:
    invented: list[str] = []
    for m in POINTER_VERBS.finditer(answer):
        raw = m.group(1).strip()
        words = raw.split()
        if not words:
            continue
        first = words[0].lower().strip(".,;:\"'`")
        if first in POINTER_STOP_WORDS or first.endswith("ing"):
            continue
        if len(words) > 1 and words[-1].lower().strip(".,;:\"'`") in POINTER_ENTITY_SUFFIXES:
            target = words[0].strip(".,;:\"'`")
        else:
            target = words[0].strip(".,;:\"'`")
        if target and not _is_real_entity(fixture_dir, target):
            invented.append(raw.strip(".,;:\"'`"))
    return sorted(set(invented))


def _refusal_checks(result: RunResult) -> list[Check]:
    answer = result.answer
    invented = sorted(
        {
            m for m in PATH_LIKE.findall(answer)
            if not _is_real_path(result.fixture_dir, m)
        }
    )
    invented_pointers = _find_invented_pointers(result.fixture_dir, answer)
    lowered = answer.lower()
    cue = any(c in lowered for c in REFUSAL_CUES)
    return [
        Check("refusal_cue", cue, "" if cue else "no refusal wording"),
        Check("no_invented_path", not invented, f"invented: {invented}" if invented else ""),
        Check(
            "no_invented_pointer",
            not invented_pointers,
            f"invented: {invented_pointers}" if invented_pointers else "",
        ),
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
