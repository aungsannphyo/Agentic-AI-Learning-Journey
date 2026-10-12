import pytest

from app.agent import PROMPTS, Prompt, get_prompt


def test_registry_keys_match_prompt_names() -> None:
    for key, prompt in PROMPTS.items():
        assert prompt.name == key


def test_unknown_prompt_lists_available_names() -> None:
    with pytest.raises(KeyError, match="baseline"):
        get_prompt("nope")


def test_grounded_is_strict_extension_of_baseline() -> None:
    base = get_prompt("baseline").text
    grounded = get_prompt("grounded-v1").text
    assert grounded.startswith(base)


def test_sha_changes_when_text_changes() -> None:
    assert Prompt("a", "x").sha != Prompt("a", "y").sha
    assert Prompt("a", "x").label.startswith("a@")


def test_every_prompt_names_only_real_tools() -> None:
    for prompt in PROMPTS.values():
        assert "list_files, read_file, search_text" in prompt.text
