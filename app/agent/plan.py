"""Plan as data. Provider-independent: the planner adapter produces
list[str]; everything downstream (state, trace, prompt injection) uses Plan.

Step ids and status are assigned by code, never by the model.
"""

from dataclasses import dataclass, field
from enum import Enum


class StepStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    DONE = "done"
    FAILED = "failed"


@dataclass
class PlanStep:
    id: int
    description: str
    status: StepStatus = StepStatus.PENDING


@dataclass
class Plan:
    steps: list[PlanStep] = field(default_factory=list)

    @classmethod
    def from_descriptions(cls, descriptions: list[str], *, max_steps: int = 8) -> "Plan":
        cleaned = [d.strip() for d in descriptions if d and d.strip()]
        return cls(
            steps=[
                PlanStep(id=i, description=d)
                for i, d in enumerate(cleaned[:max_steps], start=1)
            ]
        )

    def __len__(self) -> int:
        return len(self.steps)

    def render(self) -> str:
        """Numbered text form injected into the conversation."""
        return "\n".join(f"{s.id}. {s.description}" for s in self.steps)
