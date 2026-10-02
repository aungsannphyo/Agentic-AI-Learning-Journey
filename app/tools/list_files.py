from typing import Any

from .base import Tool
from .workspace import Workspace


class ListFilesTool(Tool):
    """List files and directories under the workspace."""

    def __init__(self, workspace: Workspace) -> None:
        self._workspace = workspace

    @property
    def name(self) -> str:
        return "list_files"

    @property
    def description(self) -> str:
        return (
            "List files and directories under a workspace-relative "
            "directory. Use an empty path for the workspace root."
        )

    @property
    def input_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": (
                        "Workspace-relative directory path. "
                        "Use an empty string for the workspace root."
                    ),
                },
            },
            "required": ["path"],
            "additionalProperties": False,
        }

    def run(self, arguments: dict[str, Any]) -> list[str]:
        path = arguments["path"]
        directory = self._workspace.resolve(path)

        if not directory.exists():
            raise FileNotFoundError(
                f"Directory does not exist: {path}"
            )

        if not directory.is_dir():
            raise NotADirectoryError(
                f"Path is not a directory: {path}"
            )

        return sorted(
            entry.name
            for entry in directory.iterdir()
        )
