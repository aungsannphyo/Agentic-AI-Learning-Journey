from typing import Any

from app.agent.decision import DecisionAction
from app.agent.decision_recovery import DecisionRecovery


class FakeStructuredClient:
    def __init__(
        self,
        responses: list[dict[str, Any]],
    ) -> None:
        self.responses = list(responses)
        self.calls = 0

    def generate_decision(
        self,
        prompt: str,
        schema: dict[str, Any],
    ) -> dict[str, Any]:
        self.calls += 1

        return self.responses.pop(0)


def test_invalid_decision_becomes_observation() -> None:
    client = FakeStructuredClient(
        responses=[
            {
                "action": "tool_call",
                "arguments": {
                    "path": "app/main.py",
                },
            }
        ]
    )

    recovery = DecisionRecovery(
        client=client,
        schema={},
    )

    decision, observation = recovery.generate(
        "Read app/main.py"
    )

    assert decision is None
    assert observation is not None

    assert observation["success"] is False
    assert (
        observation["error_type"]
        == "structured_output_validation"
    )

    assert client.calls == 1


def test_valid_decision_passes() -> None:
    client = FakeStructuredClient(
        responses=[
            {
                "action": "tool_call",
                "tool_name": "read_file",
                "arguments": {
                    "path": "app/main.py",
                },
            }
        ]
    )

    recovery = DecisionRecovery(
        client=client,
        schema={},
    )

    decision, observation = recovery.generate(
        "Read app/main.py"
    )

    assert observation is None
    assert decision is not None

    assert decision.action == DecisionAction.TOOL_CALL
    assert decision.tool_name == "read_file"
