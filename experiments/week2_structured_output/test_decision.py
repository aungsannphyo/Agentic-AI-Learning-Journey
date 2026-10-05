import pytest
from pydantic import ValidationError

from app.agent.decision import Decision, DecisionAction


def test_tool_call_decision_is_valid() -> None:
    decision = Decision(
        action=DecisionAction.TOOL_CALL,
        tool_name="read_file",
        arguments={
            "path": "app/agent/loop.py",
        },
    )

    assert decision.action == DecisionAction.TOOL_CALL
    assert decision.tool_name == "read_file"
    assert decision.arguments == {
        "path": "app/agent/loop.py",
    }


def test_final_answer_decision_is_valid() -> None:
    decision = Decision(
        action=DecisionAction.FINAL_ANSWER,
        final_answer="The file is implemented correctly.",
    )

    assert decision.action == DecisionAction.FINAL_ANSWER
    assert decision.final_answer == (
        "The file is implemented correctly."
    )


def test_tool_call_requires_tool_name() -> None:
    with pytest.raises(ValidationError):
        Decision(
            action=DecisionAction.TOOL_CALL,
            arguments={},
        )


def test_tool_call_requires_arguments() -> None:
    with pytest.raises(ValidationError):
        Decision(
            action=DecisionAction.TOOL_CALL,
            tool_name="read_file",
        )


def test_final_answer_requires_answer() -> None:
    with pytest.raises(ValidationError):
        Decision(
            action=DecisionAction.FINAL_ANSWER,
        )


def test_tool_call_cannot_have_final_answer() -> None:
    with pytest.raises(ValidationError):
        Decision(
            action=DecisionAction.TOOL_CALL,
            tool_name="read_file",
            arguments={},
            final_answer="This should not exist.",
        )


def test_final_answer_cannot_have_tool_name() -> None:
    with pytest.raises(ValidationError):
        Decision(
            action=DecisionAction.FINAL_ANSWER,
            final_answer="Done.",
            tool_name="read_file",
        )


def test_unknown_fields_are_rejected() -> None:
    with pytest.raises(ValidationError):
        Decision(
            action=DecisionAction.FINAL_ANSWER,
            final_answer="Done.",
            confidence=0.99,
        )


def test_json_schema_can_be_generated() -> None:
    schema = Decision.model_json_schema()

    assert schema["type"] == "object"
    assert "action" in schema["properties"]
    assert "tool_name" in schema["properties"]
    assert "arguments" in schema["properties"]
    assert "final_answer" in schema["properties"]
