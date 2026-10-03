from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, model_validator


class DecisionAction(str, Enum):
    TOOL_CALL = "tool_call"
    FINAL_ANSWER = "final_answer"


class Decision(BaseModel):
    """
    Machine-verifiable decision produced by the LLM.

    A Decision represents exactly one of two agent actions:

    1. tool_call
    2. final_answer

    The model is intentionally strict because this object becomes
    a trusted boundary between untrusted LLM output and the runtime.
    """

    model_config = ConfigDict(extra="forbid")

    action: DecisionAction

    tool_name: str | None = None
    arguments: dict[str, Any] | None = None
    final_answer: str | None = None

    @model_validator(mode="after")
    def validate_action_payload(self) -> "Decision":
        if self.action == DecisionAction.TOOL_CALL:
            if not self.tool_name:
                raise ValueError(
                    "tool_call decision requires tool_name"
                )

            if self.arguments is None:
                raise ValueError(
                    "tool_call decision requires arguments"
                )

            if self.final_answer is not None:
                raise ValueError(
                    "tool_call decision cannot contain final_answer"
                )

        if self.action == DecisionAction.FINAL_ANSWER:
            if not self.final_answer:
                raise ValueError(
                    "final_answer decision requires final_answer"
                )

            if self.tool_name is not None:
                raise ValueError(
                    "final_answer decision cannot contain tool_name"
                )

            if self.arguments is not None:
                raise ValueError(
                    "final_answer decision cannot contain arguments"
                )

        return self
