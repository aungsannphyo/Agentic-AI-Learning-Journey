from app.agent.plan import Plan, StepStatus
from app.agent.plan_parsing import parse_numbered_steps


def test_ids_are_assigned_by_code_starting_at_one() -> None:
    plan = Plan.from_descriptions(["find file", "read it"])
    assert [(s.id, s.status) for s in plan.steps] == [
        (1, StepStatus.PENDING),
        (2, StepStatus.PENDING),
    ]


def test_blank_steps_dropped_and_cap_applied() -> None:
    plan = Plan.from_descriptions(["a", " ", "", "b", "c"], max_steps=2)
    assert [s.description for s in plan.steps] == ["a", "b"]


def test_render_is_numbered_text() -> None:
    assert Plan.from_descriptions(["x", "y"]).render() == "1. x\n2. y"


def test_parse_numbered_and_bulleted_lines() -> None:
    text = "Plan:\n1. list files\n2) read orders.py\n- summarize\nnot a step"
    assert parse_numbered_steps(text) == [
        "list files",
        "read orders.py",
        "summarize",
    ]


def test_parse_never_raises_on_garbage() -> None:
    assert parse_numbered_steps("") == []
    assert parse_numbered_steps("\x00\n###\n") == []
