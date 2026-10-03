import pytest
from pydantic import ValidationError

from app.tools.schemas import (
    ListFilesArgs,
    ReadFileArgs,
    SearchTextArgs,
)


def test_list_files_args_defaults_to_workspace_root() -> None:
    args = ListFilesArgs()

    assert args.path == ""


def test_list_files_args_accepts_path() -> None:
    args = ListFilesArgs(
        path="app",
    )

    assert args.path == "app"


def test_read_file_args_accepts_valid_arguments() -> None:
    args = ReadFileArgs(
        path="app/main.py",
        max_bytes=10_000,
    )

    assert args.path == "app/main.py"
    assert args.max_bytes == 10_000


def test_read_file_args_rejects_empty_path() -> None:
    with pytest.raises(ValidationError):
        ReadFileArgs(
            path="",
        )


def test_read_file_args_rejects_zero_max_bytes() -> None:
    with pytest.raises(ValidationError):
        ReadFileArgs(
            path="app/main.py",
            max_bytes=0,
        )


def test_read_file_args_rejects_negative_max_bytes() -> None:
    with pytest.raises(ValidationError):
        ReadFileArgs(
            path="app/main.py",
            max_bytes=-1,
        )


def test_read_file_args_rejects_unknown_fields() -> None:
    with pytest.raises(ValidationError):
        ReadFileArgs(
            path="app/main.py",
            unexpected=True,
        )


def test_search_text_args_accepts_valid_arguments() -> None:
    args = SearchTextArgs(
        query="AgentLoop",
        path="app",
        max_results=20,
        max_file_bytes=50_000,
    )

    assert args.query == "AgentLoop"
    assert args.path == "app"
    assert args.max_results == 20
    assert args.max_file_bytes == 50_000


def test_search_text_args_rejects_empty_query() -> None:
    with pytest.raises(ValidationError):
        SearchTextArgs(
            query="",
        )


def test_search_text_args_rejects_invalid_max_results() -> None:
    with pytest.raises(ValidationError):
        SearchTextArgs(
            query="AgentLoop",
            max_results=0,
        )


def test_search_text_args_rejects_invalid_file_budget() -> None:
    with pytest.raises(ValidationError):
        SearchTextArgs(
            query="AgentLoop",
            max_file_bytes=-1,
        )
