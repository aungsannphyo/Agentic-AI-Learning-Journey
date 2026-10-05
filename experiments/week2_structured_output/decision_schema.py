from typing import Any

from .decision import Decision


def decision_json_schema() -> dict[str, Any]:
    """
    Return the JSON Schema exposed to an LLM provider
    or used by tests/documentation.
    """

    return Decision.model_json_schema()
