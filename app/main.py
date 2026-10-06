import json
import os
from pathlib import Path

from dotenv import load_dotenv

from app.agent import (
    AgentLoop,
    LoopGuard,
    ModelPricing,
    RuntimeBudget,
    TokenBudget,
)
from app.llm import OpenAIClient, ResilientClient, RetryPolicy
from app.tools import (
    ListFilesTool,
    ReadFileTool,
    SearchTextTool,
    ToolExecutor,
    ToolRegistry,
    Workspace,
)


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
    executor = ToolExecutor(registry)

    runtime_budget = RuntimeBudget(
        max_wall_time_seconds=120.0,
        per_call_timeout_seconds=30.0,
    )

    inner = OpenAIClient(
        system_prompt=(
            "You are a software engineering agent. "
            "You must ONLY call the tools explicitly provided: list_files, read_file, search_text. "
            "Never use any namespace prefixes or tools not defined (such as repo_browser). "
            "Only use workspace-relative paths. "
            "Do not invent file contents."
        ),
        timeout_seconds=runtime_budget.per_call_timeout_seconds,
    )

    client = ResilientClient(
        inner,
        RetryPolicy(
            max_attempts=5,
            base_delay_seconds=3.0,
            max_delay_seconds=25.0,
        ),
    )

    agent = AgentLoop(
        client=client,
        registry=registry,
        executor=executor,
        max_iterations=10,
        runtime_budget=runtime_budget,
        loop_guard_factory=lambda: LoopGuard(block_on_nth_call=3),
        token_budget=TokenBudget(
            max_total_tokens=int(os.getenv("AGENT_MAX_TOTAL_TOKENS", "50000"))
        ),
        pricing=pricing_from_env(),
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
        print("\n=== LLM Retry Log ===\n")
        for rec in state.llm_attempts:
            print(rec)

    print("\n=== Usage Report ===\n")
    print(json.dumps(state.usage.report(), indent=2))

    print("\n=== Execution History ===\n")
    print(state.history.to_json())


if __name__ == "__main__":
    main()
