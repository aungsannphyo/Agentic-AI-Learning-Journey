from pathlib import Path

import pytest
from pydantic import ValidationError

from evals.spec import TaskFile, load_tasks, referenced_paths

ROOT = Path(__file__).resolve().parents[1]
TASKS = ROOT / "evals" / "tasks.yaml"


@pytest.fixture(scope="module")
def spec() -> TaskFile:
    return load_tasks(TASKS)


def test_task_file_is_valid_and_sized(spec: TaskFile) -> None:
    assert 10 <= len(spec.tasks) <= 20
    assert len(spec.enabled_tasks()) >= 10


def test_fixture_directory_exists(spec: TaskFile) -> None:
    assert (ROOT / spec.fixture).is_dir()


def test_every_referenced_file_exists_in_fixture(spec: TaskFile) -> None:
    fixture = ROOT / spec.fixture
    for task in spec.tasks:
        for rel in referenced_paths(task):
            assert (fixture / rel).is_file(), f"{task.id}: missing {rel}"


def test_all_categories_are_covered(spec: TaskFile) -> None:
    covered = {t.category for t in spec.enabled_tasks()}
    assert covered >= {"find_file", "read_fact", "find_symbol", "explain", "negative"}


def test_read_fact_ground_truth_matches_fixture(spec: TaskFile) -> None:
    fixture = ROOT / spec.fixture
    for task in spec.tasks:
        if task.category != "read_fact":
            continue
        text = "".join(
            (fixture / rel).read_text(encoding="utf-8") for rel in task.must_read
        ).lower()
        assert any(v.lower() in text for v in task.expect.values), task.id


def test_find_answers_name_real_files(spec: TaskFile) -> None:
    fixture = ROOT / spec.fixture
    for task in spec.enabled_tasks():
        if task.category not in {"find_file", "find_symbol"}:
            continue
        paths = [v for v in task.expect.values if v.startswith("src/")]
        assert paths, task.id
        for rel in paths:
            assert (fixture / rel).is_file(), f"{task.id}: {rel}"


def test_negative_tasks_ask_about_things_the_fixture_lacks(spec: TaskFile) -> None:
    corpus = "".join(
        p.read_text(encoding="utf-8").lower()
        for p in (ROOT / spec.fixture).rglob("*.py")
    )
    for forbidden in ("payment", "smtp", "credit"):
        assert forbidden not in corpus


def test_fixture_stays_small() -> None:
    files = [
        p for p in (ROOT / "evals" / "fixtures" / "shop").rglob("*")
        if p.is_file() and "__pycache__" not in p.parts
    ]
    assert len(files) <= 12
    assert all(p.stat().st_size < 3_000 for p in files)


def test_disabled_edit_task_is_excluded(spec: TaskFile) -> None:
    edit = [t for t in spec.tasks if t.category == "edit"]
    assert edit
    assert all(not t.enabled for t in edit)
    assert all(t.category != "edit" for t in spec.enabled_tasks())


def test_duplicate_ids_are_rejected() -> None:
    task = {
        "id": "a", "category": "find_file", "prompt": "p",
        "expect": {"kind": "answer_contains_all", "values": ["x"]},
    }
    with pytest.raises(ValidationError, match="duplicate"):
        TaskFile.model_validate(
            {"version": 1, "fixture": "f", "tasks": [task, task]}
        )


def test_unknown_field_is_rejected() -> None:
    bad = {
        "version": 1, "fixture": "f",
        "tasks": [{
            "id": "a", "category": "find_file", "prompt": "p", "typo_field": 1,
            "expect": {"kind": "answer_contains_all", "values": ["x"]},
        }],
    }
    with pytest.raises(ValidationError):
        TaskFile.model_validate(bad)


def test_file_content_expect_requires_path() -> None:
    bad = {
        "version": 1, "fixture": "f",
        "tasks": [{
            "id": "a", "category": "edit", "prompt": "p",
            "expect": {"kind": "file_content_contains", "values": ["x"]},
        }],
    }
    with pytest.raises(ValidationError, match="requires path"):
        TaskFile.model_validate(bad)


def test_workspace_over_fixture_can_list_and_read() -> None:
    from app.tools import ListFilesTool, ReadFileTool, Workspace

    ws = Workspace(ROOT / "evals" / "fixtures" / "shop")
    assert "src" in ListFilesTool(ws).run({"path": ""})
    content = ReadFileTool(ws).run({"path": "src/config.py"})["content"]
    assert "TAX_RATE" in content
