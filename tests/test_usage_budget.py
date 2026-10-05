from pathlib import Path
from types import SimpleNamespace

import pytest

from app.agent import AgentLoop, AgentStatus
from app.agent.cost import ModelPricing, TokenBudget, UsageTracker
from app.agent.usage import Usage, extract_usage
from app.llm import FakeLLMClient, FakeResponse
from app.tools import (
    ListFilesTool, ReadFileTool, SearchTextTool,
    ToolExecutor, ToolRegistry, Workspace,
)


# ── helpers ────────────────────────────────────────────────────────────────
def _usage(i: int, o: int) -> SimpleNamespace:
    return SimpleNamespace(input_tokens=i, output_tokens=o)


def _tool_response(call_id: str, i: int, o: int) -> FakeResponse:
    return FakeResponse(
        output_text="",
        output=[
            SimpleNamespace(
                type="function_call",
                call_id=call_id,
                name="list_files",
                arguments='{"path": "."}',
            )
        ],
        usage=_usage(i, o),
    )


def _make_loop(fake_llm, **kwargs) -> AgentLoop:
    ws = Workspace(Path.cwd())
    registry = ToolRegistry()
    registry.register(ListFilesTool(ws))
    registry.register(ReadFileTool(ws))
    registry.register(SearchTextTool(ws))
    return AgentLoop(
        client=fake_llm,
        registry=registry,
        executor=ToolExecutor(registry),
        **kwargs,
    )


# ── extract_usage ──────────────────────────────────────────────────────────
def test_extract_usage_responses_api_naming() -> None:
    resp = SimpleNamespace(usage=_usage(10, 5))
    assert extract_usage(resp) == Usage(10, 5)


def test_extract_usage_chat_completions_naming() -> None:
    resp = SimpleNamespace(
        usage=SimpleNamespace(prompt_tokens=7, completion_tokens=3)
    )
    assert extract_usage(resp) == Usage(7, 3)


def test_extract_usage_returns_none_when_unreported() -> None:
    assert extract_usage(SimpleNamespace()) is None
    assert extract_usage(SimpleNamespace(usage=None)) is None
    bad = SimpleNamespace(
        usage=SimpleNamespace(input_tokens="10", output_tokens="5")
    )
    assert extract_usage(bad) is None


# ── tracker / cost ─────────────────────────────────────────────────────────
def test_tracker_accumulates_and_prices() -> None:
    tracker = UsageTracker(ModelPricing(1.0, 2.0))
    tracker.record(Usage(300_000, 100_000))
    tracker.record(Usage(200_000, 150_000))

    assert tracker.total == Usage(500_000, 250_000)
    assert tracker.cost_usd() == pytest.approx(1.0)  # 0.5 + 0.5


def test_budget_exceeded_by_tokens_uses_gte() -> None:
    tracker = UsageTracker()
    tracker.record(Usage(600, 300))

    assert tracker.exceeded(TokenBudget(
        max_total_tokens=900)) == "max_total_tokens"
    assert tracker.exceeded(TokenBudget(max_total_tokens=901)) is None


def test_budget_exceeded_by_cost() -> None:
    tracker = UsageTracker(ModelPricing(1.0, 2.0))
    tracker.record(Usage(500_000, 250_000))  # $1.00

    assert tracker.exceeded(TokenBudget(max_cost_usd=1.0)) == "max_cost_usd"


def test_unreported_usage_fails_closed() -> None:
    tracker = UsageTracker()
    tracker.record(None)

    assert tracker.exceeded(TokenBudget(
        max_total_tokens=1000)) == "usage_unreported"


def test_cost_budget_requires_pricing() -> None:
    with pytest.raises(ValueError):
        _make_loop(
            FakeLLMClient(response="x"),
            token_budget=TokenBudget(max_cost_usd=1.0),
        )


# ── loop integration ───────────────────────────────────────────────────────
def test_loop_stops_before_executing_tools_when_over_budget() -> None:
    fake = FakeLLMClient(
        response="unreachable",
        response_sequence=[
            _tool_response("c1", 400, 100),  # total 500  < 900 → execute
            _tool_response("c2", 400, 100),  # total 1000 >= 900 → STOP
            _tool_response("c3", 400, 100),
        ],
    )
    state = _make_loop(
        fake, token_budget=TokenBudget(max_total_tokens=900)
    ).run("Keep going.")

    assert state.status == AgentStatus.TOKEN_BUDGET_EXCEEDED
    assert "max_total_tokens" in (state.error or "")
    assert len(state.history) == 1          # 2nd tool call NOT executed
    assert state.iteration == 1
    assert state.usage.calls == 2


def test_final_answer_is_accepted_even_if_over_budget() -> None:
    fake = FakeLLMClient(
        response="x",
        response_sequence=[
            FakeResponse(
                output_text="Here is the answer.",
                output=[],
                usage=_usage(5000, 500),
            )
        ],
    )
    state = _make_loop(
        fake, token_budget=TokenBudget(max_total_tokens=100)
    ).run("Answer.")

    assert state.status == AgentStatus.COMPLETED
    assert state.final_response == "Here is the answer."
    assert state.usage.report()["total_tokens"] == 5500


def test_loop_fails_closed_when_provider_omits_usage() -> None:
    fake = FakeLLMClient(
        response="x",
        response_sequence=[
            FakeResponse(
                output_text="",
                output=[
                    SimpleNamespace(
                        type="function_call", call_id="c1",
                        name="list_files", arguments='{"path": "."}',
                    )
                ],
                # usage intentionally missing
            )
        ],
    )
    state = _make_loop(
        fake, token_budget=TokenBudget(max_total_tokens=10_000)
    ).run("Go.")

    assert state.status == AgentStatus.TOKEN_BUDGET_EXCEEDED
    assert "usage_unreported" in (state.error or "")
    assert len(state.history) == 0
