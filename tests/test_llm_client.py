from app.llm import FakeLLMClient


def test_fake_llm_returns_configured_response() -> None:
    llm = FakeLLMClient(
        response="Hello from fake LLM",
    )

    result = llm.ask(
        system_prompt="You are a test assistant.",
        user_prompt="Say hello.",
    )

    assert result == "Hello from fake LLM"


def test_fake_llm_records_prompt() -> None:
    llm = FakeLLMClient(
        response="test response",
    )

    llm.ask(
        system_prompt="system instruction",
        user_prompt="user request",
    )

    assert len(llm.calls) == 1

    assert llm.calls[0] == {
        "system_prompt": "system instruction",
        "user_prompt": "user request",
    }
