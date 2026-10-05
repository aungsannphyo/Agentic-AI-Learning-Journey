from pathlib import Path

import pytest

from app.tools import ListFilesTool, ReadFileTool, SearchTextTool, Workspace


@pytest.fixture
def tools():
    ws = Workspace(Path.cwd())
    return [ListFilesTool(ws), ReadFileTool(ws), SearchTextTool(ws)]


def test_schema_is_strict_compatible(tools) -> None:
    for tool in tools:
        schema = tool.input_schema
        assert schema["type"] == "object"
        assert schema["additionalProperties"] is False
        # every property is required (strict mode)
        assert set(schema["required"]) == set(schema["properties"])
        # no pydantic noise
        for spec in schema["properties"].values():
            assert "title" not in spec
            assert "default" not in spec


def test_schema_properties_match_args_model_fields(tools) -> None:
    for tool in tools:
        assert set(tool.input_schema["properties"]) == set(
            tool.args_model.model_fields
        )


def test_model_never_sees_budget_limits(tools) -> None:
    forbidden = {"max_bytes", "max_results", "max_file_bytes"}
    for tool in tools:
        assert forbidden.isdisjoint(tool.input_schema["properties"])
