import json
from typing import Any, Protocol

from pydantic import ValidationError

from .decision import Decision


class StructuredOutputError(Exception):
    """Raised when structured LLM output cannot be parsed or validated."""


class StructuredDecisionClient(Protocol):
    """
    Provider-facing abstraction for structured decision generation.

    Implementations may use:
    - constrained decoding
    - provider-native structured outputs
    - another schema-enforcing mechanism
    """

    def generate_decision(
        self,
        prompt: str,
        schema: dict[str, Any],
    ) -> dict[str, Any]:
        ...


def parse_prompt_json(raw_output: str) -> Decision:
    """
    Parse JSON produced by a prompt-based structured-output strategy.
    """

    try:
        payload: dict[str, Any] = json.loads(raw_output)
    except json.JSONDecodeError as exc:
        raise StructuredOutputError(
            f"Invalid JSON: {exc.msg}"
        ) from exc

    try:
        return Decision.model_validate(payload)
    except ValidationError as exc:
        raise StructuredOutputError(
            f"Decision schema validation failed: {exc}"
        ) from exc


def validate_structured_payload(
    payload: dict[str, Any],
) -> Decision:
    """
    Validate a provider-produced structured payload.

    The provider is responsible for constraining generation.
    The runtime still validates the result independently.
    """

    try:
        return Decision.model_validate(payload)
    except ValidationError as exc:
        raise StructuredOutputError(
            f"Decision schema validation failed: {exc}"
        ) from exc
