from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class ToolExecution:
    """Record of a single tool execution."""

    tool_name: str
    arguments: dict[str, Any]
    result: Any | None
    error: str | None
    duration_ms: float

    @property
    def success(self) -> bool:
        return self.error is None
