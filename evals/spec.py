from pathlib import Path
from typing import Literal, Self

import yaml
from pydantic import BaseModel, ConfigDict, Field, model_validator

Category = Literal[
    "find_file", "read_fact", "find_symbol", "explain", "negative", "edit"
]
ExpectKind = Literal[
    "answer_contains_all", "answer_contains_any", "file_content_contains"
]


class Expect(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: ExpectKind
    values: list[str] = Field(min_length=1)
    path: str | None = None  # file_content_contains only

    @model_validator(mode="after")
    def _check_path(self) -> Self:
        if self.kind == "file_content_contains" and not self.path:
            raise ValueError("file_content_contains requires path")
        if self.kind != "file_content_contains" and self.path is not None:
            raise ValueError("path is only valid for file_content_contains")
        return self


class Task(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(pattern=r"^[a-z0-9][a-z0-9-]*$")
    category: Category
    prompt: str = Field(min_length=1)
    expect: Expect
    must_read: list[str] = Field(default_factory=list)
    unchanged: list[str] = Field(default_factory=list)
    max_iterations: int = Field(default=8, ge=1, le=30)
    enabled: bool = True


class TaskFile(BaseModel):
    model_config = ConfigDict(extra="forbid")

    version: Literal[1]
    fixture: str
    tasks: list[Task] = Field(min_length=1)

    @model_validator(mode="after")
    def _unique_ids(self) -> Self:
        ids = [t.id for t in self.tasks]
        duplicates = sorted({i for i in ids if ids.count(i) > 1})
        if duplicates:
            raise ValueError(f"duplicate task ids: {duplicates}")
        return self

    def enabled_tasks(self) -> list[Task]:
        return [t for t in self.tasks if t.enabled]


def load_tasks(path: str | Path) -> TaskFile:
    raw = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    return TaskFile.model_validate(raw)


def referenced_paths(task: Task) -> list[str]:
    """Every fixture file a task points at (must_read, unchanged, expect.path)."""
    paths = [*task.must_read, *task.unchanged]
    if task.expect.path:
        paths.append(task.expect.path)
    return paths
