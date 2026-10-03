from typing import Any

from pydantic import ValidationError


def format_validation_error(
    tool_name: str,
    error: ValidationError,
) -> dict[str, Any]:
    """
    Convert Pydantic validation errors into a compact,
    machine-readable observation suitable for an LLM.
    """

    errors: list[dict[str, Any]] = []

    for item in error.errors():
        location = ".".join(
            str(part)
            for part in item.get("loc", ())
        )

        errors.append(
            {
                "field": location,
                "message": item.get("msg", "Invalid value"),
                "type": item.get("type", "validation_error"),
            }
        )

    return {
        "success": False,
        "error_type": "tool_argument_validation",
        "tool_name": tool_name,
        "message": (
            f"Invalid arguments for tool '{tool_name}'."
        ),
        "errors": errors,
    }
