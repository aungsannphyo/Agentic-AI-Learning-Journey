from typing import Any


def format_structured_output_error(
    error: Exception,
) -> dict[str, Any]:
    """
    Convert structured-output failures into a compact
    observation that can be sent back to the LLM.
    """

    return {
        "success": False,
        "error_type": "structured_output_validation",
        "message": str(error),
    }
