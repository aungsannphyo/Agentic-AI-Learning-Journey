from pathlib import Path

from dotenv import load_dotenv

from app.agent import AgentLoop
from app.llm import OpenAIClient
from app.tools import (
    ListFilesTool,
    ReadFileTool,
    SearchTextTool,
    ToolExecutor,
    ToolRegistry,
    Workspace,
)


def build_registry(
    workspace: Workspace,
) -> ToolRegistry:
    registry = ToolRegistry()

    registry.register(
        ListFilesTool(workspace)
    )
    registry.register(
        ReadFileTool(workspace)
    )
    registry.register(
        SearchTextTool(workspace)
    )

    return registry


def main() -> None:
    load_dotenv()

    workspace = Workspace(
        Path.cwd()
    )

    registry = build_registry(
        workspace
    )

    executor = ToolExecutor(
        registry
    )

    client = OpenAIClient(
        system_prompt=(
            "You are a software engineering agent. "
            "Use the available tools to inspect the workspace. "
            "Only use workspace-relative paths. "
            "Do not invent file contents."
        ),
    )

    agent = AgentLoop(
        client=client,
        registry=registry,
        executor=executor,
        max_iterations=10,
    )

    state = agent.run(
        "Explain the app directory and "
        "identify the main agent loop file."
    )

    print("\n=== Final Response ===\n")
    print(state.final_response)

    print("\n=== Execution History ===\n")
    print(state.history.to_json())


if __name__ == "__main__":
    main()
