"""
Day 5 Experiments — Agent error-handling and security boundary verification.

Experiment 1  Tool Error Recovery
Experiment 2  Path Traversal
Experiment 3  Huge Output (context budget foundation)
Experiment 4  Realistic Exploration Smoke Test (fake LLM)
"""

import json
from pathlib import Path
from types import SimpleNamespace

from app.agent import AgentLoop, AgentStatus
from app.llm import FakeLLMClient, FakeResponse
from tests.builders import tool_outputs
from app.tools import (
    ListFilesTool,
    ReadFileTool,
    SearchTextTool,
    ToolExecutor,
    ToolRegistry,
    Workspace,
)

# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------


def _fc(*, call_id: str, name: str, arguments: str) -> SimpleNamespace:
    """Build a fake function_call output item."""
    return SimpleNamespace(
        type="function_call",
        call_id=call_id,
        name=name,
        arguments=arguments,
    )


def _make_loop(
    fake_llm: FakeLLMClient,
    *,
    workspace: Workspace | None = None,
    max_iterations: int = 10,
    read_file_max_bytes: int = 100_000,
) -> AgentLoop:
    ws = workspace or Workspace(Path.cwd())
    registry = ToolRegistry()
    registry.register(ListFilesTool(ws))
    registry.register(ReadFileTool(ws, max_bytes=read_file_max_bytes))
    registry.register(SearchTextTool(ws))
    executor = ToolExecutor(registry)
    return AgentLoop(
        client=fake_llm,
        registry=registry,
        executor=executor,
        max_iterations=max_iterations,
    )


# ---------------------------------------------------------------------------
# Experiment 1 — Tool Error Recovery
#
# Sequence:
#   Iteration 0  read_file("does_not_exist.py")  → ERROR
#   Iteration 1  list_files(".")                 → SUCCESS
#   Iteration 2  final answer  (no tool calls)
#
# Key assertion: tool error does NOT terminate the agent.
# ---------------------------------------------------------------------------


class TestExperiment1ToolErrorRecovery:
    def test_agent_continues_after_tool_error(self) -> None:
        fake_llm = FakeLLMClient(
            response="Recovered.",
            response_sequence=[
                # Iteration 0 — asks to read a non-existent file
                FakeResponse(
                    output_text="",
                    output=[
                        _fc(
                            call_id="call_missing",
                            name="read_file",
                            arguments='{"path": "does_not_exist.py"}',
                        )
                    ],
                ),
                # Iteration 1 — recovers, calls list_files instead
                FakeResponse(
                    output_text="",
                    output=[
                        _fc(
                            call_id="call_list",
                            name="list_files",
                            arguments='{"path": "."}',
                        )
                    ],
                ),
                # Iteration 2 — final answer
                FakeResponse(output_text="Recovered.", output=[]),
            ],
        )

        loop = _make_loop(fake_llm)
        state = loop.run("Inspect the workspace.")

        assert state.status == AgentStatus.COMPLETED
        assert state.final_response == "Recovered."

    def test_failed_tool_recorded_in_history(self) -> None:
        fake_llm = FakeLLMClient(
            response="Done.",
            response_sequence=[
                FakeResponse(
                    output_text="",
                    output=[
                        _fc(
                            call_id="call_bad",
                            name="read_file",
                            arguments='{"path": "does_not_exist.py"}',
                        )
                    ],
                ),
                FakeResponse(output_text="Done.", output=[]),
            ],
        )

        loop = _make_loop(fake_llm)
        state = loop.run("Read a missing file.")

        assert len(state.history) == 1

        record = state.history.records()[0]
        assert record.tool_name == "read_file"
        assert record.success is False
        assert record.error is not None
        assert "does_not_exist" in record.error

    def test_error_observation_appended_to_conversation(self) -> None:
        """The function_call_output carrying the error must reach the LLM
        on the next iteration as a structured observation."""
        fake_llm = FakeLLMClient(
            response="Done.",
            response_sequence=[
                FakeResponse(
                    output_text="",
                    output=[
                        _fc(
                            call_id="call_err",
                            name="read_file",
                            arguments='{"path": "ghost.py"}',
                        )
                    ],
                ),
                FakeResponse(output_text="Done.", output=[]),
            ],
        )

        loop = _make_loop(fake_llm)
        loop.run("Read a ghost file.")

        outputs = tool_outputs(fake_llm.calls[1]["messages"])
        assert len(outputs) == 1
        payload = outputs[0]
        assert payload["success"] is False

    def test_hallucinated_tool_name_recovery(self) -> None:
        """When the LLM calls an unknown/hallucinated tool (e.g. repo_browser.list_files),
        ToolRegistry raises KeyError, ToolExecutor catches it as ToolExecution(success=False),
        the error is returned to the LLM, and the LLM recovers with a valid tool."""
        fake_llm = FakeLLMClient(
            response="Done.",
            response_sequence=[
                # Step 1: Hallucinated tool name
                FakeResponse(
                    output_text="",
                    output=[
                        _fc(
                            call_id="call_bad_tool",
                            name="repo_browser.list_files",
                            arguments='{"path": "."}',
                        )
                    ],
                ),
                # Step 2: Self-corrected to valid tool
                FakeResponse(
                    output_text="",
                    output=[
                        _fc(
                            call_id="call_good_tool",
                            name="list_files",
                            arguments='{"path": "."}',
                        )
                    ],
                ),
                # Step 3: Final answer
                FakeResponse(output_text="Done.", output=[]),
            ],
        )

        loop = _make_loop(fake_llm)
        state = loop.run("Inspect repository files.")

        assert state.status == AgentStatus.COMPLETED
        assert state.final_response == "Done."
        assert len(state.history) == 2

        # Record 0: Unknown tool failure
        r0 = state.history.records()[0]
        assert r0.tool_name == "repo_browser.list_files"
        assert r0.success is False
        assert "Unknown tool" in (r0.error or "")

        # Record 1: Valid tool success
        r1 = state.history.records()[1]
        assert r1.tool_name == "list_files"
        assert r1.success is True

        # Observation reached LLM in second iteration
        outputs = tool_outputs(fake_llm.calls[1]["messages"])
        assert len(outputs) == 1
        payload = outputs[0]
        assert payload["success"] is False
        assert "Unknown tool" in payload["error"]

    def test_invalid_file_recovery(self) -> None:
        """When the LLM calls read_file with a missing/invalid file path,
        ReadFileTool raises FileNotFoundError, ToolExecutor catches it as failure,
        the error observation reaches the LLM, and the LLM recovers by listing files."""
        fake_llm = FakeLLMClient(
            response="Done.",
            response_sequence=[
                # Step 1: Correct tool, wrong input (missing file)
                FakeResponse(
                    output_text="",
                    output=[
                        _fc(
                            call_id="call_bad_file",
                            name="read_file",
                            arguments='{"path": "missing.py"}',
                        )
                    ],
                ),
                # Step 2: Self-corrected to list_files
                FakeResponse(
                    output_text="",
                    output=[
                        _fc(
                            call_id="call_list",
                            name="list_files",
                            arguments='{"path": "."}',
                        )
                    ],
                ),
                # Step 3: Final answer
                FakeResponse(output_text="Done.", output=[]),
            ],
        )

        loop = _make_loop(fake_llm)
        state = loop.run("Read missing file and inspect workspace.")

        assert state.status == AgentStatus.COMPLETED
        assert state.final_response == "Done."
        assert len(state.history) == 2

        r0 = state.history.records()[0]
        assert r0.tool_name == "read_file"
        assert r0.success is False
        assert "not found" in (r0.error or "").lower()

        r1 = state.history.records()[1]
        assert r1.tool_name == "list_files"
        assert r1.success is True


# ---------------------------------------------------------------------------
# Experiment 2 — Path Traversal
#
# Agent asks read_file("../../secret.txt").
# Expected: ToolExecution.success == False, error mentions "escapes workspace".
# Agent process must NOT crash.
# ---------------------------------------------------------------------------


class TestExperiment2PathTraversal:
    def test_path_traversal_blocked_and_agent_survives(
        self, tmp_path: Path
    ) -> None:
        workspace = Workspace(tmp_path)

        fake_llm = FakeLLMClient(
            response="Handled.",
            response_sequence=[
                FakeResponse(
                    output_text="",
                    output=[
                        _fc(
                            call_id="call_trav",
                            name="read_file",
                            arguments='{"path": "../../secret.txt"}',
                        )
                    ],
                ),
                FakeResponse(output_text="Handled.", output=[]),
            ],
        )

        loop = _make_loop(fake_llm, workspace=workspace)
        state = loop.run("Read ../../secret.txt")

        assert state.status == AgentStatus.COMPLETED

    def test_path_traversal_recorded_as_failure(
        self, tmp_path: Path
    ) -> None:
        workspace = Workspace(tmp_path)

        fake_llm = FakeLLMClient(
            response="Done.",
            response_sequence=[
                FakeResponse(
                    output_text="",
                    output=[
                        _fc(
                            call_id="call_esc",
                            name="read_file",
                            arguments='{"path": "../../secret.txt"}',
                        )
                    ],
                ),
                FakeResponse(output_text="Done.", output=[]),
            ],
        )

        loop = _make_loop(fake_llm, workspace=workspace)
        state = loop.run("Escape the workspace.")

        record = state.history.records()[0]
        assert record.success is False
        assert "escapes workspace" in (record.error or "").lower()

    def test_path_traversal_error_forwarded_to_llm(
        self, tmp_path: Path
    ) -> None:
        """PermissionError must be forwarded to the LLM as an observation,
        not silently swallowed."""
        workspace = Workspace(tmp_path)

        fake_llm = FakeLLMClient(
            response="Done.",
            response_sequence=[
                FakeResponse(
                    output_text="",
                    output=[
                        _fc(
                            call_id="call_esc2",
                            name="read_file",
                            arguments='{"path": "../../etc/passwd"}',
                        )
                    ],
                ),
                FakeResponse(output_text="Done.", output=[]),
            ],
        )

        loop = _make_loop(fake_llm, workspace=workspace)
        loop.run("Read system files.")

        outputs = tool_outputs(fake_llm.calls[1]["messages"])
        assert len(outputs) == 1
        payload = outputs[0]
        assert payload["success"] is False
        assert "escapes workspace" in payload["error"].lower()


# ---------------------------------------------------------------------------
# Experiment 3 — Huge Output (context budget foundation)
#
# ReadFileTool(max_bytes=100) + 500-byte file → ValueError in ToolExecution.
# Agent records the failure and continues.
# This is the foundation for Week 9 context budget management.
# ---------------------------------------------------------------------------


class TestExperiment3HugeOutput:
    def test_oversized_file_produces_tool_failure(
        self, tmp_path: Path
    ) -> None:
        big_file = tmp_path / "big.txt"
        big_file.write_text("x" * 500, encoding="utf-8")

        workspace = Workspace(tmp_path)

        fake_llm = FakeLLMClient(
            response="Done.",
            response_sequence=[
                FakeResponse(
                    output_text="",
                    output=[
                        _fc(
                            call_id="call_big",
                            name="read_file",
                            arguments='{"path": "big.txt"}',
                        )
                    ],
                ),
                FakeResponse(output_text="Done.", output=[]),
            ],
        )

        loop = _make_loop(
            fake_llm,
            workspace=workspace,
            read_file_max_bytes=100,
        )
        state = loop.run("Read a huge file.")

        assert state.status == AgentStatus.COMPLETED

        record = state.history.records()[0]
        assert record.success is False
        assert "too large" in (record.error or "").lower()

    def test_oversized_file_error_forwarded_to_llm(
        self, tmp_path: Path
    ) -> None:
        big_file = tmp_path / "large.txt"
        big_file.write_text("y" * 500, encoding="utf-8")

        workspace = Workspace(tmp_path)

        fake_llm = FakeLLMClient(
            response="Done.",
            response_sequence=[
                FakeResponse(
                    output_text="",
                    output=[
                        _fc(
                            call_id="call_large",
                            name="read_file",
                            arguments='{"path": "large.txt"}',
                        )
                    ],
                ),
                FakeResponse(output_text="Done.", output=[]),
            ],
        )

        loop = _make_loop(
            fake_llm,
            workspace=workspace,
            read_file_max_bytes=100,
        )
        loop.run("Read large file.")

        outputs = tool_outputs(fake_llm.calls[1]["messages"])
        assert len(outputs) == 1
        payload = outputs[0]
        assert payload["success"] is False
        assert "too large" in payload["error"].lower()


# ---------------------------------------------------------------------------
# Experiment 4 — Realistic Agent Smoke Test (fake LLM)
#
# Simulates a realistic exploration sequence:
#   list_files(".") → read_file("app/agent/loop.py") → final answer
#
# The exact tool sequence is deterministically fixed here via FakeLLMClient.
# In production it is non-deterministic (model-dependent). See Eval Week 3.
# ---------------------------------------------------------------------------


class TestExperiment4RealisticExploration:
    def test_realistic_exploration_sequence(
        self, tmp_path: Path
    ) -> None:
        # Minimal workspace that resembles the real repo
        app_dir = tmp_path / "app" / "agent"
        app_dir.mkdir(parents=True)
        (app_dir / "loop.py").write_text(
            "class AgentLoop:\n    pass\n",
            encoding="utf-8",
        )

        workspace = Workspace(tmp_path)
        final_text = (
            "The agent loop is implemented in "
            "app/agent/loop.py as the AgentLoop class."
        )

        fake_llm = FakeLLMClient(
            response=final_text,
            response_sequence=[
                # Step 1 — explore directory
                FakeResponse(
                    output_text="",
                    output=[
                        _fc(
                            call_id="call_ls",
                            name="list_files",
                            arguments='{"path": "."}',
                        )
                    ],
                ),
                # Step 2 — read the loop file
                FakeResponse(
                    output_text="",
                    output=[
                        _fc(
                            call_id="call_rf",
                            name="read_file",
                            arguments='{"path": "app/agent/loop.py"}',
                        )
                    ],
                ),
                # Step 3 — final answer
                FakeResponse(output_text=final_text, output=[]),
            ],
        )

        loop = _make_loop(fake_llm, workspace=workspace)
        state = loop.run(
            "Explain the app directory and identify the main agent loop file."
        )

        assert state.status == AgentStatus.COMPLETED
        assert "AgentLoop" in (state.final_response or "")

        assert len(state.history) == 2

        records = state.history.records()
        assert records[0].tool_name == "list_files"
        assert records[0].success is True

        assert records[1].tool_name == "read_file"
        assert records[1].success is True

    def test_history_json_is_serialisable(
        self, tmp_path: Path
    ) -> None:
        """ExecutionHistory.to_json() must produce valid JSON."""
        workspace = Workspace(tmp_path)

        fake_llm = FakeLLMClient(
            response="Done.",
            response_sequence=[
                FakeResponse(
                    output_text="",
                    output=[
                        _fc(
                            call_id="call_j",
                            name="list_files",
                            arguments='{"path": "."}',
                        )
                    ],
                ),
                FakeResponse(output_text="Done.", output=[]),
            ],
        )

        loop = _make_loop(fake_llm, workspace=workspace)
        state = loop.run("Inspect workspace.")

        raw = state.history.to_json()
        parsed = json.loads(raw)

        assert isinstance(parsed, list)
        assert len(parsed) == 1
        assert parsed[0]["tool_name"] == "list_files"
        assert isinstance(parsed[0]["duration_ms"], float)


# ---------------------------------------------------------------------------
# Experiment — Max Iteration / Infinite Loop Protection
#
# Model is stuck in a loop calling list_files repeatedly without answering.
# Runtime must enforce max_iterations limit and stop the loop safely.
# ---------------------------------------------------------------------------


class TestExperimentMaxIterationsProtection:
    def test_max_iterations_stops_infinite_tool_loop(self) -> None:
        fake_llm = FakeLLMClient(
            response="Done.",
            response_sequence=[
                FakeResponse(
                    output_text="",
                    output=[
                        _fc(
                            call_id="call_1",
                            name="list_files",
                            arguments='{"path": "."}',
                        )
                    ],
                ),
                FakeResponse(
                    output_text="",
                    output=[
                        _fc(
                            call_id="call_2",
                            name="list_files",
                            arguments='{"path": "."}',
                        )
                    ],
                ),
                FakeResponse(
                    output_text="",
                    output=[
                        _fc(
                            call_id="call_3",
                            name="list_files",
                            arguments='{"path": "."}',
                        )
                    ],
                ),
                # This response should never be reached
                FakeResponse(
                    output_text="Done.",
                    output=[],
                ),
            ],
        )

        loop = _make_loop(fake_llm, max_iterations=3)
        state = loop.run("Keep inspecting the repository.")

        assert state.status == AgentStatus.MAX_ITERATIONS
        assert state.final_response is None
        assert state.iteration == 3
        assert len(state.history) == 3
