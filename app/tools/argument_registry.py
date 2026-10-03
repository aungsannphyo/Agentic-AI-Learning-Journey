from typing import Any

from pydantic import BaseModel

from app.tools.schemas import (
    ListFilesArgs,
    ReadFileArgs,
    SearchTextArgs,
)


class ToolArgumentRegistry:
    """
    Maps tool names to their Pydantic argument schemas.
    """

    def __init__(self) -> None:
        self._schemas: dict[str, type[BaseModel]] = {
            "list_files": ListFilesArgs,
            "read_file": ReadFileArgs,
            "search_text": SearchTextArgs,
        }

    def get_schema(self, tool_name: str) -> type[BaseModel]:
        try:
            return self._schemas[tool_name]
        except KeyError as exc:
            raise ValueError(
                f"No argument schema registered for tool: {tool_name}"
            ) from exc

    def validate(
        self,
        tool_name: str,
        arguments: dict[str, Any],
    ) -> BaseModel:
        schema = self.get_schema(tool_name)

        return schema.model_validate(arguments)
