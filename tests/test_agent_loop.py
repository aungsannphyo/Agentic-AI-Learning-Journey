from pathlib import Path

from app.agent import AgentLoop, AgentStatus
from app.llm import FakeLLMClient, FakeResponse
from app.llm.types import user_message
from app.tools import (
    ListFilesTool,
    ReadFileTool,
    SearchTextTool,
    ToolExecutor,
    ToolRegistry,
    Workspace,
)
from tests.builders import function_call_item as _make_function_call_item


def _make_loop(
    fake_llm: FakeLLMClient,
    *,
    max_iterations: int = 10,
) -> AgentLoop:
    workspace = Workspace(Path.cwd())

    registry = ToolRegistry()
    registry.register(ListFilesTool(workspace))
    registry.register(ReadFileTool(workspace))
    registry.register(SearchTextTool(workspace))

    executor = ToolExecutor(registry)

    return AgentLoop(
        client=fake_llm,
        registry=registry,
        executor=executor,
        max_iterations=max_iterations,
    )


# ---------------------------------------------------------------------------
# Test 1 — happy path: tool call then final answer
# ---------------------------------------------------------------------------

def test_agent_loop_completes_after_tool_call() -> None:
    """Loop runs exactly 2 iterations:
    - Iteration 0: LLM requests list_files → executed → result added
    - Iteration 1: LLM returns final answer → COMPLETED
    """
    fake_llm = FakeLLMClient(
        response="Final answer: the workspace has an app directory.",
        response_sequence=[
            # Iteration 0 — request list_files
            FakeResponse(
                output_text="",
                output=[
                    _make_function_call_item(
                        call_id="call_001",
                        name="list_files",
                        arguments='{"path": "."}',
                    )
                ],
            ),
            # Iteration 1 — final text, no tool calls
            FakeResponse(
                output_text="Final answer: the workspace has an app directory.",
                output=[],
            ),
        ],
    )

    loop = _make_loop(fake_llm)
    state = loop.run("List files in the workspace.")

    assert state.status == AgentStatus.COMPLETED
    assert state.final_response is not None and "Final answer" in state.final_response
    assert state.iteration == 1      # incremented after iteration 0 only

    # LLM was called exactly twice
    respond_calls = [
        c for c in fake_llm.calls if c.get("method") == "complete"
    ]
    assert len(respond_calls) == 2


# ---------------------------------------------------------------------------
# Test 2 — loop stops at max_iterations
# ---------------------------------------------------------------------------

def test_agent_loop_stops_at_max_iterations() -> None:
    """When every LLM response requests a tool, the loop must stop at
    max_iterations and set status = MAX_ITERATIONS, not loop forever.
    """
    # Infinite tool-call sequence — response_sequence is empty so
    # FakeLLMClient falls back to self.response (plain text, no tool calls).
    # We make it always return a tool call by pre-populating 5 responses.
    always_calls_tool = [
        FakeResponse(
            output_text="",
            output=[
                _make_function_call_item(
                    call_id=f"call_{i:03d}",
                    name="list_files",
                    arguments='{"path": "."}',
                )
            ],
        )
        for i in range(5)        # more than max_iterations=2
    ]

    fake_llm = FakeLLMClient(
        response="should not be reached",
        response_sequence=always_calls_tool,
    )

    loop = _make_loop(fake_llm, max_iterations=2)
    state = loop.run("Keep listing forever.")

    assert state.status == AgentStatus.MAX_ITERATIONS
    assert state.final_response is None
    assert state.iteration == 2     # reached the limit


# ---------------------------------------------------------------------------
# Test 3 — conversation history is built correctly
# ---------------------------------------------------------------------------

def test_agent_loop_preserves_conversation() -> None:
    """After a full tool-call cycle, the conversation must contain:
    [0] user message
    [1] function_call item (from LLM output)
    [2] function_call_output (tool result)
    """
    function_call_item = _make_function_call_item(
        call_id="call_abc",
        name="list_files",
        arguments='{"path": "."}',
    )

    fake_llm = FakeLLMClient(
        response="Done.",
        response_sequence=[
            # Iteration 0 — tool call
            FakeResponse(
                output_text="",
                output=[function_call_item],
            ),
            # Iteration 1 — final answer
            FakeResponse(
                output_text="Done.",
                output=[],
            ),
        ],
    )

    loop = _make_loop(fake_llm)
    state = loop.run("Inspect workspace.")

    conv = state.conversation

    # [0] original user message
    assert conv[0] == user_message("Inspect workspace.")

    # [1] assistant message
    assert conv[1]["kind"] == "assistant"
    assert conv[1]["items"][0]["call_id"] == "call_abc"

    # [2] tool execution result
    assert conv[2]["kind"] == "tool_result"
    assert conv[2]["call_id"] == "call_abc"

    # Final state
    assert state.status == AgentStatus.COMPLETED
    assert state.final_response == "Done."


def test_agent_loop_records_tool_execution() -> None:
    fake_llm = FakeLLMClient(
        response="Done.",
        response_sequence=[
            FakeResponse(
                output_text="",
                output=[
                    _make_function_call_item(
                        call_id="call_001",
                        name="list_files",
                        arguments='{"path": "."}',
                    )
                ],
            ),
            FakeResponse(
                output_text="Done.",
                output=[],
            ),
        ],
    )

    loop = _make_loop(fake_llm)

    state = loop.run(
        "Inspect workspace."
    )

    assert state.status == AgentStatus.COMPLETED

    assert len(state.history) == 1

    record = state.history.records()[0]

    assert record.tool_name == "list_files"
    assert record.success is True
    assert record.error is None
    assert record.duration_ms >= 0
