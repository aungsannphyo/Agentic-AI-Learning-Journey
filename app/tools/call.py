from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class ToolCall:
    """Provider-independent representation of a tool request."""

    call_id: str
    tool_name: str
    arguments: dict[str, Any]
