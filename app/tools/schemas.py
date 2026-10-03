from pydantic import BaseModel, ConfigDict, Field, field_validator


class ToolArgs(BaseModel):
    """
    Base class for all tool argument models.

    Tool arguments are treated as untrusted input coming from
    the LLM and therefore use strict validation rules.
    """

    model_config = ConfigDict(
        extra="forbid",
        str_strip_whitespace=True,
    )


class ListFilesArgs(ToolArgs):
    """
    Arguments for list_files.
    """

    path: str = ""


class ReadFileArgs(ToolArgs):
    """
    Arguments for read_file.
    """

    path: str
    max_bytes: int = Field(
        default=100_000,
        gt=0,
    )

    @field_validator("path")
    @classmethod
    def validate_path(cls, value: str) -> str:
        if not value:
            raise ValueError("path must not be empty")

        return value


class SearchTextArgs(ToolArgs):
    """
    Arguments for search_text.
    """

    query: str
    path: str = ""
    max_results: int = Field(
        default=50,
        gt=0,
    )
    max_file_bytes: int = Field(
        default=100_000,
        gt=0,
    )

    @field_validator("query")
    @classmethod
    def validate_query(cls, value: str) -> str:
        if not value:
            raise ValueError("query must not be empty")

        return value
