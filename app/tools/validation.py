import json
from typing import Any

from pydantic import ValidationError


def format_validation_error(
    tool_name: str,
    error: ValidationError,
) -> dict[str, Any]:
    """Compact, LLM-readable description of a tool-argument failure."""
    errors: list[dict[str, Any]] = [
        {
            "field": ".".join(str(part) for part in item.get("loc", ())),
            "message": item.get("msg", "Invalid value"),
            "type": item.get("type", "validation_error"),
        }
        for item in error.errors()
    ]

    return {
        "error_type": "tool_argument_validation",
        "tool_name": tool_name,
        "message": f"Invalid arguments for tool '{tool_name}'.",
        "errors": errors,
    }


def format_validation_error_json(tool_name: str, error: ValidationError) -> str:
    return json.dumps(format_validation_error(tool_name, error))
