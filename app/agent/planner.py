"""Upfront planner: one tool-less, schema-constrained LLM call.

The plan is advisory context for the executor, never control flow.
Model output is untrusted: parse failures return an outcome with plan=None
(the call's usage was still spent, so the response is always returned).
Transport failures (LLMCallFailed / DeadlineExceeded) propagate; the loop
decides to continue without a plan.
"""

from collections.abc import Callable
from dataclasses import dataclass

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from app.llm import LLMClient, LLMResponse
from app.llm.types import user_message
from app.tools.schema_utils import strict_json_schema

from .plan import Plan
from .prompts import PLANNER_V1


class PlanSpec(BaseModel):
    """Model-facing shape. ids/status are code bookkeeping, not model output."""

    model_config = ConfigDict(extra="forbid")

    steps: list[str] = Field(
        description="Ordered steps; each is one short sentence."
    )


@dataclass(frozen=True)
class PlanOutcome:
    response: LLMResponse
    plan: Plan | None
    failure: str | None = None


class Planner:
    def __init__(self, client: LLMClient, *, max_steps: int = 6) -> None:
        self._client = client
        self._max_steps = max_steps
        self._schema = strict_json_schema(PlanSpec)

    def make(
        self, task: str, should_abort: Callable[[], bool] | None = None
    ) -> PlanOutcome:
        response = self._client.complete(
            messages=[user_message(f"{PLANNER_V1.text}\n\nTask: {task}")],
            tools=[],
            should_abort=should_abort,
            output_schema=self._schema,
        )
        try:
            spec = PlanSpec.model_validate_json(response.text)
        except ValidationError as exc:
            return PlanOutcome(
                response, None, f"invalid plan JSON: {exc.error_count()} error(s)"
            )

        plan = Plan.from_descriptions(spec.steps, max_steps=self._max_steps)
        if len(plan) == 0:
            return PlanOutcome(response, None, "plan has no steps")
        return PlanOutcome(response, plan)
