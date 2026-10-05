import json
from typing import Any

from .call import ToolCall


def parse_tool_call(*, call_id: str, name: str, raw_arguments: str) -> ToolCall:
    """Parse provider tool-call arguments without ever raising.

    Model output is untrusted: invalid JSON or a non-object payload becomes
    a ToolCall carrying parse_error instead of crashing the run.
    """
    try:
        parsed: Any = json.loads(raw_arguments)
    except (json.JSONDecodeError, TypeError) as exc:
        return ToolCall(
            call_id=call_id,
            tool_name=name,
            arguments={},
            parse_error=f"arguments are not valid JSON: {exc}",
        )

    if not isinstance(parsed, dict):
        return ToolCall(
            call_id=call_id,
            tool_name=name,
            arguments={},
            parse_error=(
                "arguments must be a JSON object, "
                f"got {type(parsed).__name__}"
            ),
        )

    return ToolCall(call_id=call_id, tool_name=name, arguments=parsed)
