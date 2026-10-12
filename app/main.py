import json
import os
import time
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

from app.agent import (
    AgentLoop,
    JsonlFileSink,
    LoopGuard,
    ModelPricing,
    RuntimeBudget,
    TokenBudget,
    get_prompt,
)
from app.agent.trace import TraceEvent
from app.llm import OpenAIClient, ResilientClient, RetryPolicy
from app.tools import (
    ListFilesTool,
    ReadFileTool,
    SearchTextTool,
    ToolExecutor,
    ToolRegistry,
    Workspace,
)
from app.tools.execution import ToolExecution


class ConsoleAndFileSink:
    """Writes structured events to JSONL file and prints live turn-by-turn progress."""

    def __init__(self, file_sink: JsonlFileSink) -> None:
        self._file_sink = file_sink

    def write(self, event: TraceEvent) -> None:
        self._file_sink.write(event)
        self._print_event(event)

    def _print_event(self, event: TraceEvent) -> None:
        etype = event.type
        data = event.data

        if etype == "run_started":
            print(f"\n🚀 [Run Started] Run ID: {event.run_id}")
            print(f"📝 Prompt: {data.get('prompt')}")
            print(f"⚙️  Max Iterations: {data.get('max_iterations')}")
            print("─" * 70)

        elif etype == "plan_created":
            steps = data.get("steps", [])
            print("📋 [Planner] Upfront Plan Created:")
            for i, step in enumerate(steps, 1):
                print(f"   {i}. {step}")
            print("─" * 70)

        elif etype == "plan_failed":
            print(f"⚠️  [Planner Failed] {data.get('reason')}")

        elif etype == "llm_call":
            iteration = data.get("iteration", 0)
            thought = data.get("thought")
            latency = data.get("latency_ms", 0.0)
            in_tok = data.get("input_tokens")
            out_tok = data.get("output_tokens")
            tool_count = data.get("tool_call_count", 0)
            print(
                f"\n🤖 [Turn {iteration}] LLM Call ({latency:.0f}ms | In: {in_tok} tok, Out: {out_tok} tok)"
            )
            if thought:
                print(f"   💭 Thought: {thought}")
            if tool_count == 0:
                print("   🎯 Decision: Final Answer (No further tool calls needed)")

        elif etype == "tool_call":
            tool = data.get("tool_name")
            args = data.get("arguments", {})
            success = data.get("success")
            duration = data.get("duration_ms", 0.0)
            status_icon = "✅" if success else "❌"
            print(
                f"   🔧 Tool: {tool}({json.dumps(args)}) {status_icon} ({duration:.1f}ms)"
            )
            if not success:
                print(f"      ❌ Error: {data.get('error')}")

        elif etype == "no_progress_nudged":
            empty_count = data.get("empty_searches", 0)
            print(
                f"   ⚠️  [No-Progress Nudge] Injected note after {empty_count} consecutive empty searches!"
            )

        elif etype == "failure_nudged":
            failures = data.get("failures", 0)
            print(
                f"   ⚠️  [Failure Nudge] Injected note after {failures} consecutive tool failures!"
            )

        elif etype == "ledger_added":
            print("   📝 [Ledger Note] Appended evidence ledger recap into conversation")

        elif etype == "guard_triggered":
            guard = data.get("guard")
            detail = data.get("detail")
            print(f"   🛑 [Guard Triggered] {guard}: {detail}")

        elif etype == "run_finished":
            status = data.get("status")
            iters = data.get("iterations")
            total_tok = data.get("total_tokens")
            cost = data.get("cost_usd", 0.0)
            print("─" * 70)
            print(
                f"🏁 [Run Finished] Status: {status} | Iterations: {iters} | Total Tokens: {total_tok} | Cost: ${cost:.5f}\n"
            )


class VerboseToolExecutor:
    """Wraps ToolExecutor to log live result previews."""

    def __init__(self, inner: ToolExecutor) -> None:
        self._inner = inner

    def execute(
        self,
        *,
        tool_name: str,
        arguments: dict[str, Any],
    ) -> ToolExecution:
        res = self._inner.execute(tool_name=tool_name, arguments=arguments)
        if res.success:
            if isinstance(res.result, list):
                count = len(res.result)
                preview = (
                    f"{count} item(s): {res.result[:3]}"
                    if count > 0
                    else "0 matches"
                )
            elif isinstance(res.result, dict) and "content" in res.result:
                preview = f"{res.result.get('size_bytes', 0)} bytes read from {res.result.get('path')}"
            else:
                preview = str(res.result)
                if len(preview) > 90:
                    preview = preview[:87] + "..."
            print(f"      📄 Observation: {preview}")
        return res


def sleep_with_progress(seconds: float) -> None:
    print(
        f"\n⏳ [Rate Limit / 429] Groq TPM limit hit! Waiting {seconds:.1f}s before auto-retrying..."
    )
    time.sleep(seconds)
    print("   🔄 Resuming execution now...\n")


def build_registry(workspace: Workspace) -> ToolRegistry:
    registry = ToolRegistry()
    registry.register(ListFilesTool(workspace))
    registry.register(ReadFileTool(workspace))
    registry.register(SearchTextTool(workspace))
    return registry


def pricing_from_env() -> ModelPricing | None:
    raw_in = os.getenv("MODEL_INPUT_USD_PER_MTOK")
    raw_out = os.getenv("MODEL_OUTPUT_USD_PER_MTOK")
    if not raw_in or not raw_out:
        return None
    return ModelPricing(float(raw_in), float(raw_out))


def main() -> None:
    load_dotenv()

    workspace = Workspace(Path.cwd())
    registry = build_registry(workspace)
    raw_executor = ToolExecutor(registry)
    executor = VerboseToolExecutor(raw_executor)

    runtime_budget = RuntimeBudget(
        max_wall_time_seconds=120.0,
        per_call_timeout_seconds=30.0,
    )

    inner = OpenAIClient(
        system_prompt=get_prompt(os.getenv("AGENT_PROMPT", "baseline")).text,
        timeout_seconds=runtime_budget.per_call_timeout_seconds,
    )

    client = ResilientClient(
        inner,
        RetryPolicy(
            max_attempts=5,
            base_delay_seconds=3.0,
            max_delay_seconds=25.0,
        ),
        sleep=sleep_with_progress,
    )

    file_sink = JsonlFileSink(Path("traces") / "runs.jsonl")
    sink = ConsoleAndFileSink(file_sink)

    agent = AgentLoop(
        client=client,
        registry=registry,
        executor=executor,  # type: ignore[arg-type]
        max_iterations=10,
        runtime_budget=runtime_budget,
        loop_guard_factory=lambda: LoopGuard(block_on_nth_call=3),
        token_budget=TokenBudget(
            max_total_tokens=int(os.getenv("AGENT_MAX_TOTAL_TOKENS", "50000"))
        ),
        pricing=pricing_from_env(),
        trace=sink,
    )

    state = agent.run(
        "Explain the app directory and identify the main agent loop file."
    )

    print("\n=== Final Response ===\n")
    print(state.final_response)

    print(f"\n=== Status: {state.status.value} ===")
    if state.error:
        print(state.error)

    if state.llm_attempts:
        print("\n=== LLM Retry Log ===")
        for rec in state.llm_attempts:
            print(rec)

    print("\n=== Usage Report ===")
    print(json.dumps(state.usage.report(), indent=2))


if __name__ == "__main__":
    main()

