from pathlib import Path
from types import SimpleNamespace

from app.agent import AgentLoop, AgentStatus, LoopGuard
from app.llm import FakeLLMClient, FakeResponse
from app.tools import ListFilesTool, ToolExecutor, ToolRegistry, Workspace


def _call(call_id: str) -> FakeResponse:
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
        usage=SimpleNamespace(input_tokens=1, output_tokens=1),
    )


def _final() -> FakeResponse:
    return FakeResponse(
        output_text="done",
        output=[],
        usage=SimpleNamespace(input_tokens=1, output_tokens=1),
    )


def test_loop_guard_state_does_not_leak_between_runs() -> None:
    ws = Workspace(Path.cwd())
    registry = ToolRegistry()
    registry.register(ListFilesTool(ws))

    def make_client() -> FakeLLMClient:
        # 2 identical calls then a final answer: below threshold (3) per run
        return FakeLLMClient(
            response="unused",
            response_sequence=[_call("a"), _call("b"), _final()],
        )

    holder = {"client": make_client()}

    class SwappableClient:
        def respond_with_tools(self, **kwargs):
            return holder["client"].respond_with_tools(**kwargs)

    agent = AgentLoop(
        client=SwappableClient(),
        registry=registry,
        executor=ToolExecutor(registry),
        loop_guard_factory=lambda: LoopGuard(max_repeated_calls=3),
    )

    first = agent.run("one")
    holder["client"] = make_client()
    second = agent.run("two")

    assert first.status == AgentStatus.COMPLETED
    # With a shared guard, run 2's first call would hit count 3 → LOOP_DETECTED
    assert second.status == AgentStatus.COMPLETED
