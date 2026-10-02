# PROGRESS

## Current
Week 1 / Day 5 — Complete
Date: 2026-10-02

## Done

### Week 1 Day 1
- Project skeleton created
- Python 3.11+
- pytest / pydantic / type hints
- LLM provider abstraction
- Fake LLM client
- ADR-0001: provider-independent LLM interface

### Week 1 Day 2
- Tool abstraction
- ToolRegistry
- ListFilesTool
- Provider-independent tool definition

### Week 1 Day 3
- Native tool calling
- ToolCall
- ToolExecution
- ToolExecutor
- OpenAI/Groq tool adapter
- Single LLM → Tool → Tool Result → LLM flow

### Week 1 Day 4
- AgentStatus
- AgentState
- AgentLoop
- Multi-iteration tool calling
- max iteration termination
- FakeLLM response_sequence
- Deterministic multi-step tests
- 19/19 tests passing at checkpoint

### Week 1 Day 5
- ExecutionHistory & ExecutionRecord telemetry store
- Workspace security boundary abstraction (path traversal protection)
- ReadFileTool with UTF-8 support and context budget `max_bytes` limit
- SearchTextTool with case-insensitive search and Cognitive Complexity ≤ 15 refactoring (`_search_file()` helper)
- ListFilesTool updated to use Workspace
- Error as Observation architecture implemented (tool errors returned as observations)
- AgentLoop updated to depend on `ToolCallingClient` protocol (ADR-0001 provider independence)
- AgentLoop records tool execution history with execution timing (duration_ms)
- Output shaping: explicit `{"success": true/false}` observations for LLM
- ToolExecutor safe exception boundary (`# noqa: BLE001` intentional broad catch)
- Separation of Concerns codified: LLM (Decide & Re-plan) vs ToolExecutor (Execute safely)
- Infinite loop protection via `max_iterations` and `AgentStatus.MAX_ITERATIONS`
- Iteration counter semantics clarified: "Completed tool-decision cycles count"
- 5 Error recovery & runtime safety experiments:
  - Exp 1A: Hallucinated tool name recovery (`repo_browser.list_files` → `list_files`)
  - Exp 1B: Invalid file recovery (`read_file("missing.py")` → `FileNotFoundError` → `list_files`)
  - Exp 2: Path traversal attack blocked (`../../secret.txt` → `PermissionError`)
  - Exp 3: Huge file budget limit (`max_bytes` → `ValueError`)
  - Exp 4: Realistic repo exploration smoke test (`list_files` → `read_file` → final answer)
  - Exp 5: Max iterations infinite tool loop termination
- `app/main.py` updated with AgentLoop, Workspace, 3 tools, and telemetry JSON print
- Real API live run on Groq (`openai/gpt-oss-120b`) demonstrating live tool error self-correction
- Full test suite expanded from 19 tests to 40 tests across 9 test files (100% passing)
- Linter: 100% ruff clean

## Code State

```text
agent-runtime/
├── app/
│   ├── main.py                  (AgentLoop + Workspace + 3 Tools + Telemetry)
│   ├── agent/
│   │   ├── __init__.py          (Exports AgentLoop, AgentState, ExecutionHistory, etc.)
│   │   ├── history.py           (ExecutionRecord, ExecutionHistory)
│   │   ├── loop.py              (AgentLoop, ToolCallingClient Protocol)
│   │   ├── single_iteration.py  (Baseline single iteration loop)
│   │   └── state.py             (AgentState, AgentStatus, history field)
│   ├── llm/
│   │   ├── __init__.py
│   │   ├── client.py            (LLMClient ABC)
│   │   ├── fake_client.py       (FakeLLMClient, FakeResponse, multi-step sequence)
│   │   ├── openai_client.py     (OpenAIClient with Groq endpoint support)
│   │   └── openai_tools.py      (to_openai_tool adapter)
│   └── tools/
│       ├── __init__.py
│       ├── base.py              (Tool ABC)
│       ├── call.py              (ToolCall dataclass)
│       ├── execution.py         (ToolExecution dataclass)
│       ├── executor.py          (ToolExecutor with timing & exception boundary)
│       ├── list_files.py        (Workspace-aware ListFilesTool)
│       ├── read_file.py         (Workspace-aware ReadFileTool with size limit)
│       ├── registry.py          (ToolRegistry store)
│       ├── search_text.py       (Workspace-aware SearchTextTool, complexity ≤ 15)
│       └── workspace.py         (Workspace security boundary)
└── tests/
    ├── test_agent_loop.py       (4 tests — multi-iteration orchestration)
    ├── test_agent_state.py      (4 tests — state transitions & defaults)
    ├── test_error_recovery.py   (13 tests — error recovery & safety experiments)
    ├── test_file_tools.py       (4 tests — workspace file tools integration)
    ├── test_llm_client.py       (2 tests — fake LLM client)
    ├── test_openai_tools.py     (1 test — tool schema conversion)
    ├── test_single_iteration.py (2 tests — single iteration baseline)
    ├── test_tools.py            (7 tests — tool registry & list_files)
    └── test_workspace.py        (3 tests — path traversal & resolution)

Total: 40/40 passed (100%)
```