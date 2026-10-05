from pydantic import BaseModel, ConfigDict, Field, field_validator


class ToolArgs(BaseModel):
    """
    Base class for all tool argument models.

    Fields here are exactly what the MODEL may choose. Budget/safety
    limits (max_bytes, max_results, ...) are NOT model-controlled; they
    are tool configuration.
    """

    model_config = ConfigDict(
        extra="forbid",
        str_strip_whitespace=True,
    )


class ListFilesArgs(ToolArgs):
    path: str = Field(
        default="",
        description=(
            "Workspace-relative directory path. "
            "Use an empty string for the workspace root."
        ),
    )


class ReadFileArgs(ToolArgs):
    path: str = Field(description="Workspace-relative file path.")

    @field_validator("path")
    @classmethod
    def validate_path(cls, value: str) -> str:
        if not value:
            raise ValueError("path must not be empty")
        return value


class SearchTextArgs(ToolArgs):
    query: str = Field(description="Text to search for.")
    path: str = Field(
        default="",
        description=(
            "Workspace-relative directory or file. "
            "Use an empty string for the workspace root."
        ),
    )

    @field_validator("query")
    @classmethod
    def validate_query(cls, value: str) -> str:
        if not value:
            raise ValueError("query must not be empty")
        return value
