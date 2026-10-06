"""
Week 2 Day 4 — Runtime Guard Integration Tests
===============================================

Four integration tests that prove AgentLoop enforces every guard
condition deterministically, without real clocks or network calls.

Test A — Normal completion     → AgentStatus.COMPLETED
Test B — Max iterations        → AgentStatus.MAX_ITERATIONS
Test C — Loop detected         → AgentStatus.LOOP_DETECTED
Test D — Wall-clock timeout    → AgentStatus.TIMEOUT
"""

from collections.abc import Callable
from pathlib import Path

from app.agent import (
    AgentLoop,
    AgentStatus,
    Clock,
    LoopGuard,
    RuntimeBudget,
)
from app.llm import FakeLLMClient, FakeResponse
from app.tools import (
    ListFilesTool,
    ReadFileTool,
    SearchTextTool,
    ToolExecutor,
    ToolRegistry,
    Workspace,
)
from tests.builders import FakeClock
from tests.builders import function_call_item as _make_function_call_item


def _make_loop(
    fake_llm: FakeLLMClient,
    *,
    max_iterations: int = 10,
    runtime_budget: RuntimeBudget | None = None,
    clock: Clock | None = None,
    loop_guard_factory: Callable[[], LoopGuard] | None = None,
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
        runtime_budget=runtime_budget,
        clock=clock,
        loop_guard_factory=loop_guard_factory,
    )


# ---------------------------------------------------------------------------
# Test A — Normal completion
# ---------------------------------------------------------------------------


def test_guard_a_normal_completion() -> None:
    """
    LLM makes one tool call then returns a final answer.
    Expected: AgentStatus.COMPLETED
    """
    fake_llm = FakeLLMClient(
        response="Done.",
        response_sequence=[
            # Iteration 0 — tool call
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
            # Iteration 1 — final answer
            FakeResponse(
                output_text="Final answer: workspace listed.",
                output=[],
            ),
        ],
    )

    loop = _make_loop(fake_llm)
    state = loop.run("List files.")

    assert state.status == AgentStatus.COMPLETED
    assert state.final_response is not None
    assert "Final answer" in state.final_response


# ---------------------------------------------------------------------------
# Test B — Max iterations
# ---------------------------------------------------------------------------


def test_guard_b_max_iterations() -> None:
    """
    LLM always requests a tool call — never gives a final answer.
    Loop must stop exactly at max_iterations and set MAX_ITERATIONS.
    """
    always_tool = [
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
        for i in range(10)  # more than max_iterations=3
    ]

    fake_llm = FakeLLMClient(
        response="unreachable",
        response_sequence=always_tool,
    )

    loop = _make_loop(fake_llm, max_iterations=3)
    state = loop.run("Keep going forever.")

    assert state.status == AgentStatus.MAX_ITERATIONS
    assert state.final_response is None
    assert state.iteration == 3


# ---------------------------------------------------------------------------
# Test C — Loop detected
# ---------------------------------------------------------------------------


def test_guard_c_loop_detected() -> None:
    """
    LLM requests the identical tool call 3 times.
    LoopGuard(block_on_nth_call=3) must fire on the 3rd call
    BEFORE the tool is executed, returning LOOP_DETECTED.
    """
    repeated_call = _make_function_call_item(
        call_id="call_x",
        name="read_file",
        arguments='{"path": "app/main.py"}',
    )

    fake_llm = FakeLLMClient(
        response="unreachable",
        response_sequence=[
            FakeResponse(output_text="", output=[repeated_call]),
            FakeResponse(output_text="", output=[repeated_call]),
            FakeResponse(output_text="", output=[repeated_call]),
        ],
    )

    loop = _make_loop(
        fake_llm,
        max_iterations=10,
        loop_guard_factory=lambda: LoopGuard(block_on_nth_call=3),
    )
    state = loop.run("Read the same file.")

    assert state.status == AgentStatus.LOOP_DETECTED
    assert state.final_response is None

    # Tool executed 2 times only — 3rd call was blocked by LoopGuard
    assert len(state.history) == 2


# ---------------------------------------------------------------------------
# Test D — Wall-clock timeout
# ---------------------------------------------------------------------------


def test_guard_d_wall_clock_timeout() -> None:
    """
    FakeClock starts at 0. Budget = 10 s.
    After the first LLM call, advance the clock to 11 s.
    The second iteration's budget check fires → TIMEOUT.
    No real sleep() is used anywhere.
    """
    clock = FakeClock(value=0.0)

    fake_llm = FakeLLMClient(
        response="unreachable",
        response_sequence=[
            # Iteration 0 — tool call (clock=0 → budget OK)
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
            # Iteration 1 would be here, budget expires first
            FakeResponse(
                output_text="should not be reached",
                output=[],
            ),
        ],
    )

    loop = _make_loop(
        fake_llm,
        max_iterations=10,
        runtime_budget=RuntimeBudget(max_wall_time_seconds=10.0),
        clock=clock,
    )

    # Wrap complete to advance clock after iteration 0
    call_count = [0]
    original_complete = loop._client.complete

    def _patched_complete(**kwargs):
        result = original_complete(**kwargs)
        call_count[0] += 1
        if call_count[0] == 1:
            # Expire the budget before iteration 1 begins
            clock.value = 11.0
        return result

    loop._client.complete = _patched_complete  # type: ignore[method-assign]

    state = loop.run("List files, then keep going.")

    assert state.status == AgentStatus.TIMEOUT
    assert state.final_response is None
