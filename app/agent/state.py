from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from .history import ExecutionHistory


class AgentStatus(str, Enum):
    RUNNING = "running"
    COMPLETED = "completed"
    MAX_ITERATIONS = "max_iterations"
    TIMEOUT = "timeout"
    LOOP_DETECTED = "loop_detected"
    FAILED = "failed"


@dataclass
class AgentState:
    conversation: list[dict[str, Any]] = field(
        default_factory=list
    )
    iteration: int = 0
    status: AgentStatus = AgentStatus.RUNNING
    final_response: str | None = None
    error: str | None = None
    history: ExecutionHistory = field(
        default_factory=ExecutionHistory
    )

    @property
    def is_finished(self) -> bool:
        return self.status != AgentStatus.RUNNING
