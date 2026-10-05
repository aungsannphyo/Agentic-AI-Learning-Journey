from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class ToolCall:
    """Provider-independent representation of a tool request.

    If the model produced arguments that could not be parsed,
    `arguments` is empty and `parse_error` explains why. The call
    is NOT executed; the error goes back to the model as an observation.
    """

    call_id: str
    tool_name: str
    arguments: dict[str, Any]
    parse_error: str | None = None
