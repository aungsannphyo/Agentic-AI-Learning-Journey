from pathlib import Path

import pytest

from app.tools import (
    ListFilesTool,
    ReadFileTool,
    SearchTextTool,
    Workspace,
)


def test_list_files_uses_workspace(
    tmp_path: Path,
) -> None:
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "main.py").write_text(
        "print('hello')",
        encoding="utf-8",
    )

    workspace = Workspace(tmp_path)
    tool = ListFilesTool(workspace)

    result = tool.run(
        {"path": "src"}
    )

    assert result == ["main.py"]


def test_read_file_returns_content(
    tmp_path: Path,
) -> None:
    file_path = (
        tmp_path / "main.py"
    )

    file_path.write_text(
        "print('hello')\n",
        encoding="utf-8",
    )

    workspace = Workspace(tmp_path)
    tool = ReadFileTool(workspace)

    result = tool.run(
        {"path": "main.py"}
    )

    assert result["path"] == "main.py"
    assert result["content"] == (
        "print('hello')\n"
    )


def test_read_file_rejects_large_file(
    tmp_path: Path,
) -> None:
    file_path = (
        tmp_path / "large.txt"
    )

    file_path.write_text(
        "x" * 20,
        encoding="utf-8",
    )

    workspace = Workspace(tmp_path)
    tool = ReadFileTool(
        workspace,
        max_bytes=10,
    )

    with pytest.raises(
        ValueError,
        match="too large",
    ):
        tool.run(
            {"path": "large.txt"}
        )


def test_search_text_returns_matches(
    tmp_path: Path,
) -> None:
    src = tmp_path / "src"
    src.mkdir()

    (src / "auth.py").write_text(
        "def login():\n"
        "    return True\n",
        encoding="utf-8",
    )

    (src / "user.py").write_text(
        "class User:\n"
        "    pass\n",
        encoding="utf-8",
    )

    workspace = Workspace(tmp_path)
    tool = SearchTextTool(workspace)

    result = tool.run(
        {
            "query": "login",
            "path": "src",
        }
    )

    assert result == [
        {
            "path": "src/auth.py",
            "line": 1,
            "text": "def login():",
        }
    ]


def test_search_text_skips_environment_and_cache_dirs(tmp_path: Path) -> None:
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "a.py").write_text("needle\n", encoding="utf-8")

    for skipped in (".venv/lib", "__pycache__", "node_modules/pkg", ".git/objects"):
        d = tmp_path / skipped
        d.mkdir(parents=True)
        (d / "noise.py").write_text("needle\n", encoding="utf-8")

    result = SearchTextTool(Workspace(tmp_path)).run(
        {"query": "needle", "path": ""}
    )

    assert [r["path"] for r in result] == ["src/a.py"]


def test_search_text_can_target_a_skipped_dir_explicitly(tmp_path: Path) -> None:
    d = tmp_path / ".venv"
    d.mkdir()
    (d / "x.py").write_text("needle\n", encoding="utf-8")

    result = SearchTextTool(Workspace(tmp_path)).run(
        {"query": "needle", "path": ".venv"}
    )

    assert [r["path"] for r in result] == [".venv/x.py"]

