from pathlib import Path

from app.llm.openai_tools import to_openai_tool
from app.tools.list_files import ListFilesTool
from app.tools.workspace import Workspace


def test_tool_is_converted_to_openai_function() -> None:
    tool = ListFilesTool(Workspace(Path.cwd()))

    result = to_openai_tool(tool)

    assert result["type"] == "function"
    assert result["name"] == "list_files"
    assert result["description"] == tool.description
    assert result["parameters"] == tool.input_schema
    assert result["strict"] is True
