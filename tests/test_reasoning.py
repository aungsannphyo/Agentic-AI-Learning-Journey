from app.llm.reasoning import extract_reasoning


def test_extracts_content_reasoning_text() -> None:
    items = [
        {"type": "reasoning", "summary": [],
         "content": [{"type": "reasoning_text", "text": " read config. "}]},
        {"type": "function_call", "name": "x"},
    ]
    assert extract_reasoning(items) == "read config."


def test_falls_back_to_summary_and_joins_parts() -> None:
    items = [
        {"type": "reasoning", "summary": [{"text": "a"}], "content": None},
        {"type": "reasoning", "content": [{"text": "b"}]},
    ]
    assert extract_reasoning(items) == "a\nb"


def test_malformed_items_never_raise() -> None:
    items = [
        {"type": "reasoning", "content": "not-a-list"},
        {"type": "reasoning", "content": [None, 3, {"text": 5}, {}]},
        {"type": "reasoning"},
        {},
    ]
    assert extract_reasoning(items) == ""
