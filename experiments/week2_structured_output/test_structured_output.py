import pytest

from app.agent.decision import DecisionAction
from app.agent.structured_output import (
    StructuredOutputError,
    parse_prompt_json,
    validate_structured_payload,
)


def test_prompt_json_parses_tool_call() -> None:
    raw_output = """
    {
        "action": "tool_call",
        "tool_name": "read_file",
        "arguments": {
            "path": "app/agent/loop.py"
        }
    }
    """

    decision = parse_prompt_json(raw_output)

    assert decision.action == DecisionAction.TOOL_CALL
    assert decision.tool_name == "read_file"


def test_prompt_json_parses_final_answer() -> None:
    raw_output = """
    {
        "action": "final_answer",
        "final_answer": "The repository uses an AgentLoop."
    }
    """

    decision = parse_prompt_json(raw_output)

    assert decision.action == DecisionAction.FINAL_ANSWER
    assert decision.final_answer == (
        "The repository uses an AgentLoop."
    )


def test_prompt_json_rejects_invalid_json() -> None:
    raw_output = """
    {
        "action": "tool_call",
        "tool_name": "read_file"
    """

    with pytest.raises(StructuredOutputError, match="Invalid JSON"):
        parse_prompt_json(raw_output)


def test_prompt_json_rejects_invalid_schema() -> None:
    raw_output = """
    {
        "action": "something_invalid"
    }
    """

    with pytest.raises(
        StructuredOutputError,
        match="Decision schema validation failed",
    ):
        parse_prompt_json(raw_output)


def test_structured_payload_is_validated() -> None:
    payload = {
        "action": "tool_call",
        "tool_name": "search_text",
        "arguments": {
            "query": "AgentLoop",
        },
    }

    decision = validate_structured_payload(payload)

    assert decision.action == DecisionAction.TOOL_CALL
    assert decision.tool_name == "search_text"


def test_structured_payload_rejects_invalid_payload() -> None:
    payload = {
        "action": "tool_call",
    }

    with pytest.raises(
        StructuredOutputError,
        match="Decision schema validation failed",
    ):
        validate_structured_payload(payload)
