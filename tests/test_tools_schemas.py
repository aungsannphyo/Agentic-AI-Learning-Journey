import pytest
from pydantic import ValidationError

from app.tools.schemas import ListFilesArgs, ReadFileArgs, SearchTextArgs


def test_list_files_args_defaults_to_workspace_root() -> None:
    assert ListFilesArgs().path == ""


def test_list_files_args_accepts_path() -> None:
    assert ListFilesArgs(path="app").path == "app"


def test_read_file_args_accepts_valid_arguments() -> None:
    assert ReadFileArgs(path="app/main.py").path == "app/main.py"


def test_read_file_args_rejects_empty_path() -> None:
    with pytest.raises(ValidationError):
        ReadFileArgs(path="")


def test_read_file_args_rejects_model_supplied_limits() -> None:
    # Limits are tool config, not model-controlled.
    with pytest.raises(ValidationError):
        ReadFileArgs(path="app/main.py", max_bytes=10_000_000)


def test_search_text_args_accepts_valid_arguments() -> None:
    args = SearchTextArgs(query="AgentLoop", path="app")
    assert args.query == "AgentLoop"
    assert args.path == "app"


def test_search_text_args_rejects_empty_query() -> None:
    with pytest.raises(ValidationError):
        SearchTextArgs(query="")


def test_search_text_args_rejects_model_supplied_limits() -> None:
    with pytest.raises(ValidationError):
        SearchTextArgs(query="x", max_results=10_000)
