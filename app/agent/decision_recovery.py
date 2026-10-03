from typing import Any

from .structured_output import (
    StructuredDecisionClient,
    StructuredOutputError,
    validate_structured_payload,
)
from .validation_errors import (
    format_structured_output_error,
)


class DecisionRecovery:
    def __init__(
        self,
        client: StructuredDecisionClient,
        schema: dict[str, Any],
    ) -> None:
        self._client = client
        self._schema = schema

    def generate(
        self,
        prompt: str,
    ):
        try:
            payload = self._client.generate_decision(
                prompt,
                self._schema,
            )

            decision = validate_structured_payload(
                payload
            )

            return decision, None

        except StructuredOutputError as exc:
            return (
                None,
                format_structured_output_error(exc),
            )
