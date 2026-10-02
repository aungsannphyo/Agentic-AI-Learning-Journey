from pathlib import Path

from app.tools import ListFilesTool, ToolRegistry, Workspace


def test_list_files_tool_lists_directory() -> None:
    tool = ListFilesTool(Workspace(Path.cwd()))

    result = tool.run({"path": "."})

    assert isinstance(result, list)
    assert "app" in result
    assert "tests" in result


def test_list_files_tool_definition() -> None:
    tool = ListFilesTool(Workspace(Path.cwd()))

    definition = tool.definition()

    assert definition["name"] == "list_files"
    assert "description" in definition
    assert definition["input_schema"]["type"] == "object"


def test_registry_registers_and_resolves_tool() -> None:
    registry = ToolRegistry()
    tool = ListFilesTool(Workspace(Path.cwd()))

    registry.register(tool)

    resolved = registry.get("list_files")

    assert resolved is tool


def test_registry_exposes_tool_definitions() -> None:
    registry = ToolRegistry()

    registry.register(ListFilesTool(Workspace(Path.cwd())))

    definitions = registry.definitions()

    assert len(definitions) == 1
    assert definitions[0]["name"] == "list_files"


def test_registry_rejects_duplicate_tool() -> None:
    registry = ToolRegistry()

    registry.register(ListFilesTool(Workspace(Path.cwd())))

    try:
        registry.register(ListFilesTool(Workspace(Path.cwd())))
    except ValueError as exc:
        assert "already registered" in str(exc)
    else:
        raise AssertionError(
            "Expected duplicate registration to fail"
        )


def test_registry_rejects_unknown_tool() -> None:
    registry = ToolRegistry()

    try:
        registry.get("does_not_exist")
    except KeyError as exc:
        assert "Unknown tool" in str(exc)
    else:
        raise AssertionError(
            "Expected unknown tool lookup to fail"
        )


def test_tool_call_representation() -> None:
    from app.tools.call import ToolCall

    call = ToolCall(
        call_id="call_123",
        tool_name="list_files",
        arguments={"path": "src"},
    )

    assert call.call_id == "call_123"
    assert call.tool_name == "list_files"
    assert call.arguments == {
        "path": "src"
    }
