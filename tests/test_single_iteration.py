from pathlib import Path
from types import SimpleNamespace

from app.agent.single_iteration import run_single_iteration
from app.llm.fake_client import FakeLLMClient, FakeResponse
from app.tools.executor import ToolExecutor
from app.tools.list_files import ListFilesTool
from app.tools.registry import ToolRegistry
from app.tools.workspace import Workspace


def test_single_iteration_with_no_tool_calls_returns_response() -> None:
    """When the model returns no tool calls, the response is returned directly."""
    registry = ToolRegistry()
    executor = ToolExecutor(registry)

    fake_llm = FakeLLMClient(response="No tools needed.")

    result = run_single_iteration(
        client=fake_llm,
        executor=executor,
        tools=registry.list(),
        user_prompt="Hello.",
    )

    assert result.output_text == "No tools needed."
    assert len(fake_llm.calls) == 1
    assert fake_llm.calls[0]["user_prompt"] == "Hello."


def test_single_iteration_executes_tool_and_returns_final_response() -> None:
    registry = ToolRegistry()
    registry.register(ListFilesTool(Workspace(Path.cwd())))

    executor = ToolExecutor(registry)

    fake_llm = FakeLLMClient(
        response="The workspace contains an app directory.",
        first_response=FakeResponse(
            output_text="",
            output=[
                SimpleNamespace(
                    type="function_call",
                    call_id="call_123",
                    name="list_files",
                    arguments='{"path": "."}',
                )
            ],
        ),
    )

    result = run_single_iteration(
        client=fake_llm,
        executor=executor,
        tools=registry.list(),
        user_prompt="Inspect the workspace.",
    )

    assert result.output_text == (
        "Final response after tool execution."
    )

    assert len(fake_llm.calls) == 2

    assert fake_llm.calls[0]["tools"] == [
        "list_files"
    ]

    conversation = fake_llm.calls[1]["conversation"]

    assert conversation[0] == {
        "role": "user",
        "content": "Inspect the workspace.",
    }

    assert conversation[1].type == "function_call"
    assert conversation[1].call_id == "call_123"

    assert conversation[2]["type"] == "function_call_output"
    assert conversation[2]["call_id"] == "call_123"
