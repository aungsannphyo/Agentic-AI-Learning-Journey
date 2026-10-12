from pathlib import Path

from app.agent import AgentLoop, AgentStatus, InMemorySink
from app.agent.planner import Planner
from app.llm import ErrorKind, FakeLLMClient, FakeResponse, LLMCallFailed
from app.tools import ListFilesTool, ToolExecutor, ToolRegistry, Workspace


def _loop(client: object, tmp_path: Path, sink: InMemorySink, *, plan: bool) -> AgentLoop:
    registry = ToolRegistry()
    registry.register(ListFilesTool(Workspace(tmp_path)))
    return AgentLoop(
        client=client,  # type: ignore[arg-type]
        registry=registry,
        executor=ToolExecutor(registry),
        trace=sink,
        use_plan=plan,
    )


def test_planner_parses_valid_json() -> None:
    client = FakeLLMClient('{"steps": ["list files", "read orders"]}')
    outcome = Planner(client).make("q")
    assert outcome.plan is not None
    assert [s.description for s in outcome.plan.steps] == ["list files", "read orders"]
    assert client.calls[0]["tools"] == []
    assert client.output_schemas[0] is not None


def test_planner_invalid_json_returns_no_plan_but_keeps_response() -> None:
    outcome = Planner(FakeLLMClient("not json")).make("q")
    assert outcome.plan is None
    assert outcome.failure is not None
    assert outcome.response is not None  # usage was spent


def test_planner_rejects_empty_and_extra_fields() -> None:
    assert Planner(FakeLLMClient('{"steps": [" "]}')).make("q").plan is None
    assert Planner(FakeLLMClient('{"steps": ["a"], "x": 1}')).make("q").plan is None


def test_loop_injects_plan_traces_it_and_counts_usage(tmp_path: Path) -> None:
    client = FakeLLMClient(
        "unused",
        response_sequence=[
            FakeResponse('{"steps": ["list files", "read orders"]}'),
            FakeResponse("done"),
        ],
    )
    sink = InMemorySink()
    state = _loop(client, tmp_path, sink, plan=True).run("q")

    assert state.status == AgentStatus.COMPLETED
    assert state.plan is not None
    assert len(state.plan) == 2
    assert client.output_schemas[0] is not None
    assert client.output_schemas[1] is None
    assert "1. list files" in client.calls[1]["messages"][0]["text"]
    assert state.usage.calls == 2  # planner call + executor call
    assert sink.types().index("plan_created") < sink.types().index("llm_call")


def test_planner_transport_failure_does_not_stop_the_run(tmp_path: Path) -> None:
    inner = FakeLLMClient("unused", response_sequence=[FakeResponse("done")])

    class PlannerDown:
        def complete(self, *, messages, tools, should_abort=None, output_schema=None):  # type: ignore[no-untyped-def]
            if output_schema is not None:
                raise LLMCallFailed("down", attempts=1, kind=ErrorKind.TRANSIENT)
            return inner.complete(messages=messages, tools=tools, should_abort=should_abort)

    sink = InMemorySink()
    state = _loop(PlannerDown(), tmp_path, sink, plan=True).run("q")
    assert state.status == AgentStatus.COMPLETED
    assert state.plan is None
    assert "plan_failed" in sink.types()
    assert inner.calls[0]["messages"][0]["text"] == "q"  # prompt untouched


def test_plan_disabled_makes_no_planner_call(tmp_path: Path) -> None:
    client = FakeLLMClient("done")
    state = _loop(client, tmp_path, InMemorySink(), plan=False).run("q")
    assert state.plan is None
    assert client.output_schemas == [None]
