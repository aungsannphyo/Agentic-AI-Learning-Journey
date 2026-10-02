from pathlib import Path

import pytest

from app.tools import Workspace


def test_workspace_resolves_relative_path(
    tmp_path: Path,
) -> None:
    workspace = Workspace(tmp_path)

    resolved = workspace.resolve(
        "src"
    )

    assert resolved == (
        tmp_path / "src"
    ).resolve()


def test_workspace_allows_nested_path(
    tmp_path: Path,
) -> None:
    workspace = Workspace(tmp_path)

    resolved = workspace.resolve(
        "src/app/main.py"
    )

    assert resolved == (
        tmp_path / "src/app/main.py"
    ).resolve()


def test_workspace_blocks_path_traversal(
    tmp_path: Path,
) -> None:
    workspace = Workspace(tmp_path)

    with pytest.raises(
        PermissionError,
        match="escapes workspace",
    ):
        workspace.resolve(
            "../../secret.txt"
        )
