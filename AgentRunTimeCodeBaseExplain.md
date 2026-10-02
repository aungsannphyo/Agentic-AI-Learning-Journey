# Agent Runtime — Complete Codebase Explanation & Code Dump
> ChatGPT သို့မဟုတ် အခြား LLM များသို့ တစ်ခုလုံး paste လုပ်၍ မေးမြန်းလေ့လာနိုင်ရန် project တစ်ခုလုံးရှိ source code, tests, configuration နှင့် architecture explanation များကို single-file အဖြစ် စုစည်းထားသည်။

---

## 🗂️ Complete Project Structure (Day 5 Updated)

```
agent-runtime/
├── app/
│   ├── __init__.py                  ← Package marker
│   ├── main.py                      ← 🔄 Entry point (AgentLoop + Workspace + 3 Tools + History JSON)
│   ├── agent/
│   │   ├── __init__.py              ← 🔄 Agent module exports (AgentLoop, AgentState, ExecutionHistory, etc.)
│   │   ├── history.py               ← 🆕 Telemetry & Execution audit log (ExecutionRecord, ExecutionHistory)
│   │   ├── loop.py                  ← 🔄 Multi-iteration Orchestrator (ToolCallingClient Protocol, Error as Observation)
│   │   ├── single_iteration.py      ← Day 3 Single iteration loop (foundation)
│   │   └── state.py                 ← 🔄 Agent state machine (AgentState, AgentStatus, history tracking)
│   ├── llm/
│   │   ├── __init__.py              ← LLM module exports
│   │   ├── client.py                ← Abstract base interface (LLMClient)
│   │   ├── fake_client.py           ← 🔄 Deterministic test LLM (respond_with_tools, response_sequence)
│   │   ├── openai_client.py         ← 🔄 Real OpenAI/Groq implementation (respond_with_tools, function calling)
│   │   └── openai_tools.py          ← Tool to OpenAI schema adapter (to_openai_tool)
│   └── tools/
│       ├── __init__.py              ← 🔄 Tools module exports (All 3 tools, Workspace, Executor, Registry)
│       ├── base.py                  ← Abstract Tool base class (name, description, schema, run)
│       ├── call.py                  ← ToolCall data model
│       ├── execution.py             ← ToolExecution data model (with duration_ms and success property)
│       ├── executor.py              ← Tool runner (execution timing & exception boundary)
│       ├── list_files.py            ← 🔄 Workspace-aware directory listing tool
│       ├── read_file.py             ← 🆕 Workspace-aware UTF-8 file reader with max_bytes limit
│       ├── registry.py              ← Tool lookup registry (named registry with validation)
│       ├── search_text.py           ← 🆕 Text search tool (case-insensitive, Cognitive Complexity <= 15)
│       └── workspace.py             ← 🆕 Security boundary (path traversal defense)
├── tests/
│   ├── test_agent_loop.py           ← 🔄 Multi-iteration loop tests (Workspace-aware, 4 tests)
│   ├── test_agent_state.py          ← 🆕 AgentState & status unit tests (4 tests)
│   ├── test_error_recovery.py       ← 🆕 Day 5 Experiments (Error Recovery, Path Traversal, Huge Output, Smoke Test - 13 tests)
│   ├── test_file_tools.py           ← 🆕 Integration tests for Workspace file tools (4 tests)
│   ├── test_llm_client.py           ← Fake LLM unit tests (2 tests)
│   ├── test_openai_tools.py         ← 🔄 OpenAI tool conversion test (Workspace-aware, 1 test)
│   ├── test_single_iteration.py     ← 🔄 Single iteration loop tests (Workspace-aware, 2 tests)
│   ├── test_tools.py                ← 🔄 Tool & Registry unit tests (Workspace-aware, 7 tests)
│   └── test_workspace.py            ← 🆕 Workspace path resolution & security tests (3 tests)
├── docs/
│   └── adr/
│       └── 0001-llm-provider-abstraction.md ← Architectural Decision Record (Provider Independence)
├── conftest.py                      ← Pytest path configuration
├── pyproject.toml                   ← Build & dependencies (Hatchling, OpenAI, Pydantic, Pytest, Ruff)
├── .env.example                     ← Environment variable template
├── .gitignore                       ← 🔄 Git ignore rules (includes notes/journey docs)
├── README.md                        ← Project overview & design goals
└── PROGRESS.md                      ← Day-by-day learning milestones log
```

---

## 🧠 Architecture & Mental Model (Day 5 Multi-Turn Loop)

```
                     ┌──────────────────┐
                     │   User Prompt    │
                     └────────┬─────────┘
                              │
                              ▼
                       ┌─────────────┐
                       │  AgentLoop  │ ◄──────────────────────────────┐
                       └──────┬──────┘                                │
                              │                                       │
            ┌─────────────────┴─────────────────┐                     │
            ▼                                   ▼                     │
   ToolCallingClient                       ToolExecutor               │
      (Protocol)                                │                     │
            │                             ┌─────┴──────┐              │
    LLM API / Fake                        │  Registry  │              │
            │                             └─────┬──────┘              │
     ToolCall requests                          │                     │
            │                     ┌─────────────┼─────────────┐       │
            │                     ▼             ▼             ▼       │
            │                list_files     read_file    search_text  │
            │                     └─────────────┬─────────────┘       │
            │                                   ▼                     │
            │                               Workspace                 │
            │                          (Security Boundary)            │
            │                                   │                     │
            │                             ToolExecution               │
            │                            (success/error)              │
            │                                   │                     │
            │                           ExecutionHistory              │
            │                             (Telemetry)                 │
            │                                   │                     │
            └───────────► New Observation ──────┴─────────────────────┘
                          (appended to conversation history for next turn)
```

### Core Concepts in Agentic Software
1. **AgentLoop is Orchestration, NOT Intelligence**: LLM က decision ချတယ်၊ Tool က action လုပ်တယ်၊ `Workspace` က security ထိန်းတယ်၊ `ToolExecutor` က execution time နဲ့ error ကိုဖမ်းတယ်၊ `AgentState` က state သိမ်းတယ်၊ `AgentLoop` က အားလုံးကို coordinate လုပ်ပေးတာသာ ဖြစ်တယ်။
2. **Error as Observation**: Normal software မှာ error ဖြစ်ရင် crash/exception တက်တယ်။ Agentic software မှာ tool error ဟာ observation အသစ်တစ်ခုဖြစ်ပြီး LLM ဆီ `{"success": false, "error": "..."}` အနေနဲ့ ပြန်ပို့ပေးရမယ်။ ဒါမှ LLM က self-heal / re-plan လုပ်နိုင်မယ်။
3. **Workspace Security Boundary**: Path traversal attacks (`../../secret.txt`) တွေကို tool တိုင်းမှာ duplicate စစ်မယ့်အစား `Workspace` class တစ်ခုတည်းမှာ centralized boundary ထားရှိပြီး resolve လုပ်တယ်။
4. **Context Budget Foundation**: `read_file` တွင် `max_bytes` limit ထားခြင်း၊ `search_text` တွင် `max_results` limit ထားခြင်းတို့သည် LLM context window မပြည့်လျှံစေရန် Week 9 context budget အတွက် အခြေခံဖြစ်တယ်။

### 🏛️ Separation of Concerns in Agent Runtime (တာဝန်ခွဲဝေမှုစည်းမျဉ်း)

| Component | Responsibility (တာဝန်) | မလုပ်သင့်သည့်အရာ (Anti-pattern) |
|---|---|---|
| **LLM** | **Decide** — မည်သည့် tool ကို မည်သည့် arguments ဖြင့် ခေါ်မည်ကို ဆုံးဖြတ်ခြင်း၊ Error observation ရရှိပါက Re-plan လုပ်ခြင်း | Execution ကိုယ်တိုင်လုပ်ခြင်း မရှိ |
| **AgentLoop** | **Coordinate** — LLM response ရယူခြင်း၊ tools များသို့ dispatch လုပ်ခြင်း၊ history သိမ်းခြင်း၊ iteration limit စောင့်ကြည့်ခြင်း | Intelligence မပါဝင်၊ Re-planning မလုပ် |
| **ToolExecutor** | **Execute safely** — Tool registry မှ lookup လုပ်ခြင်း၊ run ခြင်း၊ execution time တိုင်းတာခြင်း၊ error အားလုံးကို catch လုပ်ခြင်း | Re-plan မလုပ်ပါ! Error တက်ပါက `ToolExecution(success=False)` ပြန်ပေးရုံသာ |
| **Tool** | **Perform operation** — Concrete OS/File logic (ဖိုင်ဖတ်ခြင်း၊ ရှာဖွေခြင်း) ကို လုပ်ဆောင်ခြင်း | Security စစ်ဆေးမှုများကို tool တိုင်းတွင် duplicate မလုပ်ရ |
| **Workspace** | **Enforce security** — Centralized path resolution နှင့် Path Traversal (`../../`) တားဆီးခြင်း | File parsing / searching logic မပါဝင်ရ |

> **အရေးကြီးသော မှတ်ချက်:** `ToolExecutor` သည် re-plan မလုပ်ပါ။ ToolExecutor ၏ တာဝန်သည် `execute → result / error` သာ ဖြစ်သည်။ Re-planning ကို LLM ကသာ ဦးဆောင်လုပ်ဆောင်သည်။

### ⏱️ Iteration Counter — "Completed Tool-Decision Cycles Count"

Agent loop တွင် iteration counter ကို အောက်ပါအတိုင်း design လုပ်ထားသည်:

```python
if state.iteration >= self._max_iterations:
    state.status = AgentStatus.MAX_ITERATIONS
    break
...
# Tool execution finished
state.iteration += 1
```

- `iteration` သည် **"Completed tool-decision cycles count"** (ပြီးမြောက်သွားသော tool-decision လှည့်ပတ်မှုအရေအတွက်) ကို ကိုယ်စားပြုသည်။
- LLM က ပထမအကြိမ်တွင် tool call မလုပ်ဘဲ final answer ချက်ချင်းဖြေပါက iteration တိုးစရာမလိုဘဲ `iteration == 0` ဖြင့် ပြီးဆုံးသည်။
- Tool call တစ်ခု သို့မဟုတ် တစ်တွဲကို execute လုပ်ပြီး observation အဖြစ် conversation ထဲ ပြန်ထည့်ပြီးမှသာ `iteration += 1` တိုးသည်။ ထို့ကြောင့် 1st tool decision cycle ပြီးပါက `iteration == 1`၊ 2nd tool decision cycle ပြီးပါက `iteration == 2` ဖြစ်သည်။
- Model တွင် bug ဖြစ်ပြီး tool ကို အဆုံးမရှိ ဆက်တိုက်ခေါ်နေပါက `state.iteration >= max_iterations` condition ကြောင့် Infinite loop မဖြစ်ဘဲ `MAX_ITERATIONS` status ဖြင့် လုံခြုံစွာ ရပ်တန့်စေသည့် **Runtime Guard** ဖြစ်သည်။

---

## 📁 PART 1: CORE RUNTIME SOURCE CODE (`app/`)
### 1. `app/main.py` — Program Entry Point 🔄

**ဘာလုပ်သလဲ:** Program ကို command line (`python -m app.main`) မှ စတင် run ရာ entry point ဖြစ်သည်။ `Workspace`, `ToolRegistry`, `ToolExecutor`, `OpenAIClient`, `AgentLoop` များကို ချိတ်ဆက်ပြီး agent အား repository အား စူးစမ်းရှာဖွေစေကာ final response နှင့် execution history JSON ကို print ထုတ်ပေးသည်။

| Function / Block | ဘာလုပ်သလဲ |
|---|---|
| `build_registry(workspace)` | `Workspace` instance ကို လက်ခံပြီး `ListFilesTool`, `ReadFileTool`, `SearchTextTool` ၃ ခုစလုံးကို register လုပ်ထားသော `ToolRegistry` ကို build လုပ်ပေးသည်။ |
| `main()` | `.env` ကို load လုပ်သည် → Workspace(cwd) ဆောက်သည် → ToolRegistry & ToolExecutor ဆောက်သည် → OpenAIClient setup လုပ်သည် → AgentLoop run သည် → Final Response & Execution History JSON print ထုတ်သည်။ |

```python
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
```

### 2. `app/agent/__init__.py` — Agent Module Exports 🔄

**ဘာလုပ်သလဲ:** `app.agent` package မှ အဓိက classes နှင့် functions များကို သန့်ရှင်းစွာ export လုပ်ပေးသော file ဖြစ်သည်။

| Exported Symbol | Type | တာဝန် |
|---|---|---|
| `AgentLoop` | Class | Multi-turn agent orchestrator loop |
| `AgentState` | Dataclass | Loop state machine (status, iteration, conversation, history) |
| `AgentStatus` | Enum | Loop states (`RUNNING`, `COMPLETED`, `MAX_ITERATIONS`, `FAILED`) |
| `ExecutionHistory` | Class | Tool execution audit log & telemetry store |
| `ExecutionRecord` | Dataclass | Single tool execution snapshot record |
| `run_single_iteration` | Function | Day 3 single iteration helper |

```python
from .history import ExecutionHistory, ExecutionRecord
from .loop import AgentLoop
from .single_iteration import run_single_iteration
from .state import AgentState, AgentStatus

__all__ = [
    "AgentLoop",
    "AgentState",
    "AgentStatus",
    "ExecutionHistory",
    "ExecutionRecord",
    "run_single_iteration",
]
```

### 3. `app/agent/state.py` — Agent State Machine 🔄

**ဘာလုပ်သလဲ:** Agent loop တစ်ခုလုံး၏ mutable runtime state ကို ထိန်းသိမ်းသော dataclass ဖြစ်သည်။ Conversation history, current iteration counter, loop status, final response, error message နှင့် runtime telemetry အတွက် `ExecutionHistory` တို့ ပါဝင်သည်။

| Attribute / Property | Type | ရှင်းလင်းချက် |
|---|---|---|
| `conversation` | `list[dict[str, Any]]` | LLM နှင့် အပြန်အလှန်ပြောဆိုထားသော message list |
| `iteration` | `int` | လက်ရှိရောက်ရှိနေသော iteration အကြိမ်အရေအတွက် |
| `status` | `AgentStatus` | Loop ရဲ့ current status (`RUNNING`, `COMPLETED`, `MAX_ITERATIONS`, `FAILED`) |
| `final_response` | `str \| None` | Agent ပြီးဆုံးချိန်တွင် user မြင်တွေ့ရမည့် final answer |
| `error` | `str \| None` | Agent crash/failure ဖြစ်ခဲ့ပါက သိမ်းဆည်းမည့် error message |
| `history` | `ExecutionHistory` | Tool run တိုင်း၏ telemetry record များကို စုဆောင်းထားသော audit log |
| `is_finished` (property) | `bool` | `status != AgentStatus.RUNNING` ဖြစ်ပါက `True` ဖြစ်ပြီး while loop ကို ရပ်တန့်စေသည်။ |

```python
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from .history import ExecutionHistory


class AgentStatus(str, Enum):
    RUNNING = "running"
    COMPLETED = "completed"
    MAX_ITERATIONS = "max_iterations"
    FAILED = "failed"


@dataclass
class AgentState:
    conversation: list[dict[str, Any]] = field(
        default_factory=list
    )
    iteration: int = 0
    status: AgentStatus = AgentStatus.RUNNING
    final_response: str | None = None
    error: str | None = None
    history: ExecutionHistory = field(
        default_factory=ExecutionHistory
    )

    @property
    def is_finished(self) -> bool:
        return self.status != AgentStatus.RUNNING
```

### 4. `app/agent/history.py` — Execution Telemetry & Audit Log 🆕

**ဘာလုပ်သလဲ:** Agent အသုံးပြုသွားသော tool executions တိုင်း၏ tool name, arguments, success/failure status, result/error နှင့် duration (milliseconds) များကို စနစ်တကျ မှတ်တမ်းတင်ပေးသော runtime telemetry class pair ဖြစ်သည်။

| Class / Method | တာဝန် |
|---|---|
| `ExecutionRecord` (dataclass) | Tool တစ်ခုချင်းစီ run ခဲ့သည့် snapshot (immutable `frozen=True`): `tool_name`, `arguments`, `success`, `result`, `error`, `duration_ms` |
| `ExecutionHistory.__init__()` | `_records` list ကို initialize လုပ်သည်။ |
| `ExecutionHistory.add(record)` | `ExecutionRecord` အသစ်တစ်ခုကို append လုပ်သည်။ |
| `ExecutionHistory.records()` | Records အားလုံး၏ copy list ကို ပြန်ပေးသည်။ |
| `ExecutionHistory.to_dicts()` | Records များကို dictionary list အဖြစ်ပြောင်းသည်။ |
| `ExecutionHistory.to_json()` | Telemetry data ကို formatted JSON string (`indent=2`) အဖြစ် serialize လုပ်ပေးသည်။ |
| `ExecutionHistory.__len__()` | `len(state.history)` ဟု တိုက်ရိုက် syntax သုံးနိုင်ရန် implement လုပ်ထားသည်။ |

```python
import json
from dataclasses import asdict, dataclass
from typing import Any


@dataclass(frozen=True)
class ExecutionRecord:
    tool_name: str
    arguments: dict[str, Any]
    success: bool
    result: Any
    error: str | None
    duration_ms: float


class ExecutionHistory:
    """Stores tool executions for a single agent run."""

    def __init__(self) -> None:
        self._records: list[ExecutionRecord] = []

    def add(self, record: ExecutionRecord) -> None:
        self._records.append(record)

    def records(self) -> list[ExecutionRecord]:
        return list(self._records)

    def to_dicts(self) -> list[dict[str, Any]]:
        return [
            asdict(record)
            for record in self._records
        ]

    def to_json(self) -> str:
        return json.dumps(
            self.to_dicts(),
            indent=2,
            default=str,
        )

    def __len__(self) -> int:
        return len(self._records)
```

### 5. `app/agent/loop.py` — Agent Loop Orchestrator 🔄

**ဘာလုပ်သလဲ:** LLM ၏ decision နှင့် tool executions များကို multi-iteration loop အဖြစ် orchestrate လုပ်ပေးသော core class ဖြစ်သည်။ `ToolCallingClient` Protocol ကို အသုံးပြုထားသဖြင့် LLM provider အပေါ် တိုက်ရိုက် မမှီခိုဘဲ decoupling ဖြစ်စေသည်။ Tool error များကို conversation ထဲသို့ observation အဖြစ် ထည့်သွင်းပေးပြီး execution history ကိုပါ တွဲဖက်မှတ်တမ်းတင်သည်။

| Member | တာဝန် |
|---|---|
| `ToolCallingClient` (Protocol) | ADR-0001 အရ LLM client တိုင်း implement လုပ်ရမည့် `respond_with_tools` method contract |
| `AgentLoop.__init__()` | `client`, `registry`, `executor`, `max_iterations` (default 10) တို့ကို inject လုပ်သည်။ |
| `AgentLoop.run(user_prompt)` | While loop ပတ်၍ LLM ဆီ မေးသည် → tool calls မပါတော့ပါက COMPLETED → tool calls ပါက executor ဖြင့် run သည် → history တွင် record ထည့်သည် → output shape (`{"success": bool, ...}`) အဖြစ် observation ပြန်ပို့သည်။ |

```python
import json
from typing import Any, Protocol

from app.tools import Tool, ToolCall, ToolExecutor, ToolRegistry

from .history import ExecutionRecord
from .state import AgentState, AgentStatus


class ToolCallingClient(Protocol):
    def respond_with_tools(
        self,
        *,
        conversation: list[dict[str, Any]],
        tools: list[Tool],
    ) -> tuple[Any, list[ToolCall]]:
        ...


class AgentLoop:
    """Orchestrates LLM decisions and tool execution."""

    def __init__(
        self,
        client: ToolCallingClient,
        registry: ToolRegistry,
        executor: ToolExecutor,
        max_iterations: int = 10,
    ) -> None:
        self._client = client
        self._registry = registry
        self._executor = executor
        self._max_iterations = max_iterations

    def run(
        self,
        user_prompt: str,
    ) -> AgentState:
        state = AgentState(
            conversation=[
                {
                    "role": "user",
                    "content": user_prompt,
                }
            ]
        )

        while not state.is_finished:
            if state.iteration >= self._max_iterations:
                state.status = AgentStatus.MAX_ITERATIONS
                break

            response, tool_calls = (
                self._client.respond_with_tools(
                    conversation=state.conversation,
                    tools=self._registry.list(),
                )
            )

            state.conversation.extend(
                response.output
            )

            if not tool_calls:
                state.final_response = (
                    response.output_text
                )
                state.status = AgentStatus.COMPLETED
                break

            for tool_call in tool_calls:
                execution = self._executor.execute(
                    tool_name=tool_call.tool_name,
                    arguments=tool_call.arguments,
                )

                state.history.add(
                    ExecutionRecord(
                        tool_name=execution.tool_name,
                        arguments=execution.arguments,
                        success=execution.success,
                        result=execution.result,
                        error=execution.error,
                        duration_ms=execution.duration_ms,
                    )
                )

                output: dict[str, Any]

                if execution.success:
                    output = {
                        "success": True,
                        "result": execution.result,
                    }
                else:
                    output = {
                        "success": False,
                        "error": execution.error,
                    }

                state.conversation.append(
                    {
                        "type": "function_call_output",
                        "call_id": tool_call.call_id,
                        "output": json.dumps(
                            output,
                            default=str,
                        ),
                    }
                )

            state.iteration += 1

        return state
```

### 6. `app/agent/single_iteration.py` — Single Iteration Loop (Day 3 Foundation)

**ဘာလုပ်သလဲ:** LLM → Tool → LLM ဆိုသည့် single cycle တစ်ကြိမ်တည်း loop ကို စတင်လေ့လာစဉ်က ရေးသားခဲ့သော architectural baseline ဖြစ်သည်။ Multi-turn loop မတိုင်မီ single step စမ်းသပ်ရန်နှင့် baseline logic အဖြစ် ထိန်းသိမ်းထားသည်။

| Component | တာဝန် |
|---|---|
| `ToolCallingClient` (Protocol) | `ask_with_tools` နှင့် `continue_with_tool_outputs` contract |
| `run_single_iteration()` | 1 turn သာ run သော function ဖြစ်ပြီး tool call ကို execute လုပ်ကာ conversation ထဲ result ပြန်ထည့်ပြီး final response ရယူသည်။ |

```python
import json
from typing import Any, Protocol

from app.tools import Tool, ToolCall, ToolExecutor


class ToolCallingClient(Protocol):
    def ask_with_tools(
        self,
        *,
        user_prompt: str,
        tools: list[Tool],
    ) -> tuple[Any, list[ToolCall]]:
        ...

    def continue_with_tool_outputs(
        self,
        *,
        conversation: list[dict[str, Any]],
        tools: list[Tool],
    ) -> Any:
        ...


def run_single_iteration(
    *,
    client: ToolCallingClient,
    executor: ToolExecutor,
    tools: list[Tool],
    user_prompt: str,
) -> Any:
    response, tool_calls = client.ask_with_tools(
        user_prompt=user_prompt,
        tools=tools,
    )

    if not tool_calls:
        return response

    conversation: list[dict[str, Any]] = [
        {
            "role": "user",
            "content": user_prompt,
        },
        *response.output,
    ]

    for call in tool_calls:
        execution = executor.execute(
            tool_name=call.tool_name,
            arguments=call.arguments,
        )

        print(
            f"[Tool Call] "
            f"{call.tool_name}({call.arguments})"
        )

        if execution.success:
            print(f"[Tool Result] {execution.result}")
        else:
            print(f"[Tool Error] {execution.error}")

        conversation.append(
            {
                "type": "function_call_output",
                "call_id": call.call_id,
                "output": json.dumps(
                    execution.result
                    if execution.success
                    else {
                        "error": execution.error,
                    }
                ),
            }
        )

    return client.continue_with_tool_outputs(
        conversation=conversation,
        tools=tools,
    )
```

### 7. `app/llm/__init__.py` — LLM Module Exports

**ဘာလုပ်သလဲ:** `app.llm` package အတွက် export interface ဖြစ်သည်။

| Exported Symbol | တာဝန် |
|---|---|
| `LLMClient` | Abstract base class interface |
| `OpenAIClient` | Concrete OpenAI/Groq API client |
| `FakeLLMClient` | Test များအတွက် deterministic fake client |
| `FakeResponse` | Fake LLM response mock data object |
| `to_openai_tool` | Tool specification ကို OpenAI function calling schema သို့ convert လုပ်ပေးသော function |

```python
# llm sub-package

from .client import LLMClient
from .fake_client import FakeLLMClient, FakeResponse
from .openai_client import OpenAIClient
from .openai_tools import to_openai_tool

__all__ = [
    "FakeLLMClient",
    "FakeResponse",
    "LLMClient",
    "OpenAIClient",
    "to_openai_tool",
]
```

### 8. `app/llm/client.py` — Abstract LLM Interface (ADR-0001)

**ဘာလုပ်သလဲ:** LLM provider တိုင်းလိုက်နာရမည့် interface (contract) ဖြစ်သည်။ Provider agnostic ဖြစ်စေရန် ရည်ရွယ်သည်။

| Method | တာဝန် |
|---|---|
| `ask(*, system_prompt, user_prompt) -> str` | LLM သို့ prompt ပို့ပြီး text output ပြန်ယူသည့် abstract method |

```python
from abc import ABC, abstractmethod


class LLMClient(ABC):
    """Provider-independent interface for language model clients."""

    @abstractmethod
    def ask(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
    ) -> str:
        """Send a prompt to the LLM and return generated text."""
        raise NotImplementedError
```

### 9. `app/llm/fake_client.py` — Test Fake LLM Client 🔄

**ဘာလုပ်သလဲ:** Pytest tests များတွင် network calls မသုံးဘဲ deterministic tests များ စိတ်ချလက်ချ run နိုင်ရန် ရေးသားထားသော Fake client ဖြစ်သည်။ Multi-turn testing အတွက် `respond_with_tools()` နှင့် `response_sequence` queue ပါဝင်သည်။

| Method / Property | တာဝန် |
|---|---|
| `FakeResponse` | `output_text`, `output` (function calls), `id` တို့ပါဝင်သော fake LLM response |
| `__init__()` | Single response သို့မဟုတ် multi-step sequence (`response_sequence`) ကို လက်ခံသည်။ |
| `respond_with_tools()` | Multi-turn `AgentLoop` tests အတွက် sequence ထဲမှ `FakeResponse` တစ်ခုချင်း pop ထုတ်ပြီး tool calls များကို extract လုပ်ပေးသည်။ |
| `_extract_tool_calls()` | LLM response output ထဲရှိ `function_call` item များကို internal `ToolCall` objects အဖြစ် ပြောင်းပေးသည်။ |
| `calls` | Test assertion များတွင် LLM ခေါ်ဆိုမှုများကို verify လုပ်နိုင်ရန် request များကို စုဆောင်းထားသော list |

```python
import json
from dataclasses import dataclass, field
from typing import Any, Optional

from app.tools import ToolCall

from .client import LLMClient


@dataclass
class FakeResponse:
    output_text: str
    output: list[Any] = field(default_factory=list)
    id: str = "fake-response-123"


class FakeLLMClient(LLMClient):
    """Deterministic LLM implementation for tests."""

    def __init__(
        self,
        response: str,
        *,
        first_response: Optional["FakeResponse"] = None,
        response_sequence: list["FakeResponse"] | None = None,
    ) -> None:
        self.response = response
        self._first_response = first_response
        # Multi-step sequence for AgentLoop tests.
        # Each call to respond_with_tools pops the next FakeResponse.
        self._response_sequence: list[FakeResponse] = (
            list(response_sequence) if response_sequence else []
        )
        self.calls: list[dict[str, Any]] = []

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _extract_tool_calls(self, response: "FakeResponse") -> list[ToolCall]:
        return [
            ToolCall(
                call_id=item.call_id,
                tool_name=item.name,
                arguments=json.loads(item.arguments),
            )
            for item in response.output
            if item.type == "function_call"
        ]

    # ------------------------------------------------------------------
    # LLMClient interface (simple ask)
    # ------------------------------------------------------------------

    def ask(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
    ) -> str:
        self.calls.append(
            {
                "system_prompt": system_prompt,
                "user_prompt": user_prompt,
            }
        )

        return self.response

    # ------------------------------------------------------------------
    # Single-iteration tool calling (used by run_single_iteration)
    # ------------------------------------------------------------------

    def ask_with_tools(
        self,
        *,
        user_prompt: str,
        tools: list[Any],
    ) -> tuple[FakeResponse, list[Any]]:
        self.calls.append(
            {
                "user_prompt": user_prompt,
                "tools": [tool.name for tool in tools],
            }
        )

        first_response = self._first_response or FakeResponse(
            output_text=self.response,
        )

        return first_response, self._extract_tool_calls(first_response)

    def continue_with_tool_outputs(
        self,
        *,
        conversation: list[dict[str, Any]],
        tools: list[Any],
    ) -> FakeResponse:
        self.calls.append(
            {
                "method": "continue_with_tool_outputs",
                "conversation": conversation,
                "tools": [tool.name for tool in tools],
            }
        )

        return FakeResponse(
            output_text="Final response after tool execution.",
            output=[],
        )

    # ------------------------------------------------------------------
    # Multi-turn method used by AgentLoop
    # ------------------------------------------------------------------

    def respond_with_tools(
        self,
        *,
        conversation: list[dict[str, Any]],
        tools: list[Any],
    ) -> tuple["FakeResponse", list[ToolCall]]:
        """Pop the next FakeResponse from response_sequence.

        When the sequence is exhausted, returns a plain response with
        no tool calls so the loop terminates cleanly.
        """
        self.calls.append(
            {
                "method": "respond_with_tools",
                "conversation": list(conversation),
                "tools": [tool.name for tool in tools],
            }
        )

        if self._response_sequence:
            fake_response = self._response_sequence.pop(0)
        else:
            fake_response = FakeResponse(output_text=self.response)

        return fake_response, self._extract_tool_calls(fake_response)
```

### 10. `app/llm/openai_client.py` — Real OpenAI/Groq Client 🔄

**ဘာလုပ်သလဲ:** OpenAI SDK (`client.responses.create`) ကို အသုံးပြု၍ Groq endpoint (`api.groq.com/openai/v1`) မှတဆင့် real LLM calls များ ပြုလုပ်ပေးသော implementation ဖြစ်သည်။ Single iteration နှင့် Multi-turn `AgentLoop` နှစ်မျိုးစလုံးအတွက် support လုပ်ထားသည်။

| Method | တာဝန် |
|---|---|
| `__init__()` | `OPENAI_API_KEY`, `OPENAI_MODEL`, `OPENAI_TEMPERATURE` များကို load လုပ်ပြီး Groq base_url ဖြင့် client initialize လုပ်သည်။ |
| `ask()` | Tool မပါသော ရိုးရိုး prompt မေးမြန်းခြင်း |
| `ask_with_tools()` | Prompt နှင့် tools များကို ပို့ပြီး ပထမဆုံး response နှင့် tool calls များကို ပြန်ယူသည်။ |
| `continue_with_tool_outputs()` | Tool execution results များကို conversation တွင် ပေါင်းထည့်ပြီး ဆက်မေးသည်။ |
| `respond_with_tools()` | Multi-iteration `AgentLoop` အတွက် conversation history အပြည့်အစုံနှင့် tools များကို ပေးပို့ကာ tool call requests များကို ပြန်လည် parse လုပ်ပေးသည်။ |

```python
import json
import os
from typing import Any

from openai import OpenAI

from app.tools import Tool, ToolCall

from .client import LLMClient
from .openai_tools import to_openai_tool


class OpenAIClient(LLMClient):
    """OpenAI implementation of the provider-independent LLMClient."""

    def __init__(
        self,
        *,
        model: str | None = None,
        temperature: float | None = None,
        system_prompt: str | None = None,
    ) -> None:
        self._client = OpenAI(
            api_key=os.environ["OPENAI_API_KEY"],
            base_url="https://api.groq.com/openai/v1",
        )

        self._model = model or os.getenv(
            "OPENAI_MODEL",
            "openai/gpt-oss-120b",
        )

        self._temperature = (
            temperature
            if temperature is not None
            else float(
                os.getenv(
                    "OPENAI_TEMPERATURE",
                    "0.2",
                )
            )
        )

        self._system_prompt: str | None = system_prompt

    def ask(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
    ) -> str:
        response = self._client.responses.create(
            model=self._model,
            instructions=system_prompt,
            input=user_prompt,
            temperature=self._temperature,
        )

        return response.output_text

    def ask_with_tools(
        self,
        *,
        user_prompt: str,
        tools: list[Tool],
    ) -> tuple[Any, list[ToolCall]]:
        response = self._client.responses.create(
            model=self._model,
            instructions=self._system_prompt,
            input=user_prompt,
            tools=[
                to_openai_tool(tool)
                for tool in tools
            ],
            temperature=self._temperature,
        )

        tool_calls: list[ToolCall] = []

        for item in response.output:
            if item.type != "function_call":
                continue

            tool_calls.append(
                ToolCall(
                    call_id=item.call_id,
                    tool_name=item.name,
                    arguments=json.loads(item.arguments),
                )
            )

        return response, tool_calls

    def continue_with_tool_outputs(
        self,
        *,
        conversation: list[dict[str, Any]],
        tools: list[Tool],
    ) -> Any:
        """Continue a response after executing model-requested tools."""

        return self._client.responses.create(
            model=self._model,
            instructions=self._system_prompt,
            input=conversation,
            tools=[
                to_openai_tool(tool)
                for tool in tools
            ],
            temperature=self._temperature,
        )

    def respond_with_tools(
        self,
        *,
        conversation: list[dict[str, Any]],
        tools: list[Tool],
    ) -> tuple[Any, list[ToolCall]]:
        """Single unified call used by AgentLoop on every iteration.

        Sends the full conversation history and available tools to the
        model, then extracts any tool-call requests from the response.
        """
        response = self._client.responses.create(
            model=self._model,
            instructions=self._system_prompt,
            input=conversation,
            tools=[to_openai_tool(tool) for tool in tools],
            temperature=self._temperature,
        )

        tool_calls: list[ToolCall] = []

        for item in response.output:
            if item.type != "function_call":
                continue

            tool_calls.append(
                ToolCall(
                    call_id=item.call_id,
                    tool_name=item.name,
                    arguments=json.loads(item.arguments),
                )
            )

        return response, tool_calls
```

### 11. `app/llm/openai_tools.py` — Tool Format Converter

**ဘာလုပ်သလဲ:** ကျွန်ုပ်တို့၏ internal `Tool` object specification ကို OpenAI Functions / Tools JSON schema သို့ convert လုပ်ပေးသော adapter ဖြစ်သည်။

| Function | တာဝန် |
|---|---|
| `to_openai_tool(tool: Tool) -> dict` | `tool.name`, `tool.description`, `tool.input_schema` များကိုယူပြီး `{"type": "function", "name": ..., "strict": True}` schema သို့ ပြောင်းပေးသည်။ |

```python
from typing import Any

from app.tools import Tool


def to_openai_tool(tool: Tool) -> dict[str, Any]:
    """Convert an internal Tool into an OpenAI function tool."""

    return {
        "type": "function",
        "name": tool.name,
        "description": tool.description,
        "parameters": tool.input_schema,
        "strict": True,
    }
```

### 12. `app/tools/__init__.py` — Tools Module Exports 🔄

**ဘာလုပ်သလဲ:** `app.tools` package မှ Tool base classes, concrete file tools, `Workspace` security boundary နှင့် execution components များကို export လုပ်ပေးသော file ဖြစ်သည်။

| Exported Symbol | တာဝန် |
|---|---|
| `Tool` | Abstract base class |
| `ToolCall`, `ToolExecution` | Data models |
| `ToolExecutor`, `ToolRegistry` | Execution runtime & lookup store |
| `Workspace` | Security boundary class (Path traversal protection) |
| `ListFilesTool` | Workspace-aware directory listing |
| `ReadFileTool` | Workspace-aware UTF-8 reader with size limit |
| `SearchTextTool` | Workspace-aware text search tool |

```python
from .base import Tool
from .call import ToolCall
from .execution import ToolExecution
from .executor import ToolExecutor
from .list_files import ListFilesTool
from .read_file import ReadFileTool
from .registry import ToolRegistry
from .search_text import SearchTextTool
from .workspace import Workspace

__all__ = [
    "ListFilesTool",
    "ReadFileTool",
    "SearchTextTool",
    "Tool",
    "ToolCall",
    "ToolExecution",
    "ToolExecutor",
    "ToolRegistry",
    "Workspace",
]
```

### 13. `app/tools/base.py` — Abstract Tool Base Class

**ဘာလုပ်သလဲ:** Agent စနစ်ရှိ Tool အားလုံး လိုက်နာရမည့် Abstract Base Class (ABC) ဖြစ်သည်။ Tool တစ်ခုချင်းစီ၏ name, description, schema နှင့် execution logic ကို standard ဖြစ်စေသည်။

| Property / Method | တာဝန် |
|---|---|
| `name` (abstract property) | Tool ၏ နာမည် (e.g. `list_files`, `read_file`) |
| `description` (abstract property) | Tool အကြောင်း ရှင်းလင်းချက် (LLM က ဖတ်ရှု၍ ရွေးချယ်ရန်) |
| `input_schema` (abstract property) | Tool input argument များအတွက် JSON Schema |
| `run(arguments)` (abstract method) | Argument များကို လက်ခံပြီး အမှန်တကယ် execute လုပ်ရမည့် logic |
| `definition()` | Provider-agnostic metadata dictionary (`name`, `description`, `input_schema`) ပြန်ပေးသည်။ |

```python
from abc import ABC, abstractmethod
from typing import Any


class Tool(ABC):
    """Base abstraction for all agent tools."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Unique tool name exposed to the LLM."""
        raise NotImplementedError

    @property
    @abstractmethod
    def description(self) -> str:
        """Human/model-readable description of the tool."""
        raise NotImplementedError

    @property
    @abstractmethod
    def input_schema(self) -> dict[str, Any]:
        """JSON Schema describing the tool's input."""
        raise NotImplementedError

    @abstractmethod
    def run(self, arguments: dict[str, Any]) -> Any:
        """Execute the tool with validated arguments."""
        raise NotImplementedError

    def definition(self) -> dict[str, Any]:
        """Return provider-independent tool metadata."""
        return {
            "name": self.name,
            "description": self.description,
            "input_schema": self.input_schema,
        }
```

### 14. `app/tools/call.py` — ToolCall Data Class

**ဘာလုပ်သလဲ:** LLM မှ tool call ခေါ်ဆိုရန် တောင်းဆိုလာသည့် request ကို provider-independent အဖြစ် ကိုယ်စားပြုသော immutable dataclass ဖြစ်သည်။

| Field | တာဝန် |
|---|---|
| `call_id` (`str`) | Model က ပေးပို့သော call correlation ID (e.g. `call_001`) |
| `tool_name` (`str`) | ခေါ်ဆိုလိုသော tool နာမည် |
| `arguments` (`dict[str, Any]`) | Tool သို့ ပေးပို့မည့် parsed arguments dictionary |

```python
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class ToolCall:
    """Provider-independent representation of a tool request."""

    call_id: str
    tool_name: str
    arguments: dict[str, Any]
```

### 15. `app/tools/execution.py` — ToolExecution Data Class

**ဘာလုပ်သလဲ:** Tool တစ်ခု run ပြီးချိန်တွင် ထွက်ပေါ်လာသော execution result, error message နှင့်ကြာချိန် (duration) တို့ကို သိမ်းဆည်းသော immutable dataclass ဖြစ်သည်။

| Field / Property | တာဝန် |
|---|---|
| `tool_name` (`str`) | Run ခဲ့သော tool နာမည် |
| `arguments` (`dict[str, Any]`) | ပေးပို့ခဲ့သော input arguments |
| `result` (`Any \| None`) | အောင်မြင်ပါက ပြန်ရသော data (failure ဖြစ်ပါက `None`) |
| `error` (`str \| None`) | ကျရှုံးပါက ဖြစ်ပေါ်သော error message (success ဖြစ်ပါက `None`) |
| `duration_ms` (`float`) | Execution ကြာချိန် (milliseconds) |
| `success` (property) | `self.error is None` ဖြစ်ပါက `True` ဖြစ်သည်။ |

```python
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class ToolExecution:
    """Record of a single tool execution."""

    tool_name: str
    arguments: dict[str, Any]
    result: Any | None
    error: str | None
    duration_ms: float

    @property
    def success(self) -> bool:
        return self.error is None
```

### 16. `app/tools/executor.py` — Tool Executor (Execution & Exception Boundary)

**ဘာလုပ်သလဲ:** `ToolRegistry` မှ tool ကို ရှာဖွေပြီး timing တွက်ကာ run ပေးသော class ဖြစ်သည်။ မည်သည့် exception ဖြစ်ပေါ်ပါစေ executor boundary တွင် catch လုပ်ကာ `ToolExecution(success=False, error=str(exc))` အဖြစ် ပြောင်းပေးသဖြင့် agent process မ crash ဘဲ အလုပ်ဆက်လုပ်နိုင်သည်။

| Method | တာဝန် |
|---|---|
| `__init__(registry)` | `ToolRegistry` ကို inject လုပ်သည်။ |
| `execute(*, tool_name, arguments)` | `perf_counter()` ဖြင့် အချိန်စမှတ်သည် → registry မှ tool ယူသည် → `tool.run(arguments)` ခေါ်သည် → exception တက်ပါက catch လုပ်ပြီး `ToolExecution` ပြန်ပေးသည်။ |

```python
from time import perf_counter
from typing import Any

from .execution import ToolExecution
from .registry import ToolRegistry


class ToolExecutor:
    """Executes registered tools and records execution metadata."""

    def __init__(self, registry: ToolRegistry) -> None:
        self._registry = registry

    def execute(
        self,
        *,
        tool_name: str,
        arguments: dict[str, Any],
    ) -> ToolExecution:
        started_at = perf_counter()

        try:
            tool = self._registry.get(tool_name)

            result = tool.run(arguments)

            return ToolExecution(
                tool_name=tool_name,
                arguments=arguments,
                result=result,
                error=None,
                duration_ms=(
                    perf_counter() - started_at
                ) * 1000,
            )

        except Exception as exc:  # noqa: BLE001
            return ToolExecution(
                tool_name=tool_name,
                arguments=arguments,
                result=None,
                error=str(exc),
                duration_ms=(
                    perf_counter() - started_at
                ) * 1000,
            )
```

### 17. `app/tools/workspace.py` — Workspace Security Boundary 🆕

**ဘာလုပ်သလဲ:** Agentic AI စနစ်၏ အရေးကြီးဆုံး Security Boundary ဖြစ်သည်။ Path traversal attacks (ဥပမာ `../../secret.txt` သို့မဟုတ် `/etc/passwd`) ကို ကာကွယ်ရန် paths များကို workspace root အောက်တွင်သာ resolve လုပ်ခွင့်ပြုပြီး အပြင်သို့ လွတ်ထွက်ပါက `PermissionError` raise လုပ်သည်။ Tool တိုင်းတွင် duplicate code ရေးစရာမလိုဘဲ centralized security boundary ဖြစ်စေသည်။

| Method / Property | တာဝန် |
|---|---|
| `__init__(root)` | Workspace root directory ကို resolve လုပ်ပြီး absolute path အဖြစ် သိမ်းဆည်းသည်။ |
| `root` (property) | Resolved root `Path` object ကို ပြန်ပေးသည်။ |
| `resolve(path)` | `(self._root / path).resolve()` တွက်ပြီး `candidate.relative_to(self._root)` စစ်ဆေးသည်။ Root အပြင်ရောက်ပါက `PermissionError("Path escapes workspace: ...")` raise လုပ်သည်။ |

```python
from pathlib import Path


class Workspace:
    """Resolves paths while enforcing a workspace boundary."""

    def __init__(self, root: str | Path) -> None:
        self._root = Path(root).resolve()

    @property
    def root(self) -> Path:
        return self._root

    def resolve(self, path: str) -> Path:
        candidate = (
            self._root / path
        ).resolve()

        try:
            candidate.relative_to(self._root)
        except ValueError as exc:
            raise PermissionError(
                f"Path escapes workspace: {path}"
            ) from exc

        return candidate
```

### 18. `app/tools/list_files.py` — ListFiles Tool 🔄

**ဘာလုပ်သလဲ:** Workspace အတွင်းရှိ directory နှင့် files များကို list လုပ်ပေးသော tool ဖြစ်သည်။ `Workspace` boundary ကို အသုံးပြုသဖြင့် workspace ပြင်ပ directory များကို list လုပ်ခွင့်မရှိပါ။

| Method / Property | တာဝန် |
|---|---|
| `__init__(workspace)` | `Workspace` instance ကို လက်ခံသည်။ |
| `name` | `"list_files"` |
| `description` | "List files and directories under a workspace-relative directory..." |
| `input_schema` | `{"path": {"type": "string"}}` (empty string သည် workspace root ကို ဆိုလိုသည်) |
| `run(arguments)` | `self._workspace.resolve(path)` ဖြင့် စစ်ဆေးသည် → directory မရှိပါက `FileNotFoundError`၊ directory မဟုတ်ပါက `NotADirectoryError` raise သည် → sorted file names list ပြန်ပေးသည်။ |

```python
from typing import Any

from .base import Tool
from .workspace import Workspace


class ListFilesTool(Tool):
    """List files and directories under the workspace."""

    def __init__(self, workspace: Workspace) -> None:
        self._workspace = workspace

    @property
    def name(self) -> str:
        return "list_files"

    @property
    def description(self) -> str:
        return (
            "List files and directories under a workspace-relative "
            "directory. Use an empty path for the workspace root."
        )

    @property
    def input_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": (
                        "Workspace-relative directory path. "
                        "Use an empty string for the workspace root."
                    ),
                },
            },
            "required": ["path"],
            "additionalProperties": False,
        }

    def run(self, arguments: dict[str, Any]) -> list[str]:
        path = arguments["path"]
        directory = self._workspace.resolve(path)

        if not directory.exists():
            raise FileNotFoundError(
                f"Directory does not exist: {path}"
            )

        if not directory.is_dir():
            raise NotADirectoryError(
                f"Path is not a directory: {path}"
            )

        return sorted(
            entry.name
            for entry in directory.iterdir()
        )
```

### 19. `app/tools/read_file.py` — ReadFile Tool 🆕

**ဘာလုပ်သလဲ:** Workspace အတွင်းရှိ UTF-8 text file တစ်ခု၏ content ကို ဖတ်ရှုပေးသော tool ဖြစ်သည်။ ဖိုင်အရွယ်အစား limit (`max_bytes=100_000`) ပါရှိပြီး Context Window budget မကျော်လွန်စေရန် ထိန်းချုပ်ပေးသည်။

| Method / Property | တာဝန် |
|---|---|
| `__init__(workspace, *, max_bytes)` | `Workspace` နှင့် အများဆုံးဖတ်ခွင့်ရှိသော bytes အရေအတွက် (default: 100,000 bytes) ကို သတ်မှတ်သည်။ |
| `name` | `"read_file"` |
| `input_schema` | `{"path": {"type": "string"}}` |
| `run(arguments)` | `resolve(path)` ဖြင့် စစ်ဆေးသည် → ဖိုင်မရှိပါက `FileNotFoundError` → directory ဖြစ်နေပါက `IsADirectoryError` → `max_bytes` ကျော်ပါက `ValueError` → UTF-8 မဟုတ်ပါက `ValueError` raise လုပ်သည်။ အောင်မြင်ပါက `{"path": ..., "content": ..., "size_bytes": ...}` dictionary ပြန်ပေးသည်။ |

```python
from typing import Any

from .base import Tool
from .workspace import Workspace


class ReadFileTool(Tool):
    """Read a UTF-8 text file from the workspace."""

    def __init__(
        self,
        workspace: Workspace,
        *,
        max_bytes: int = 100_000,
    ) -> None:
        self._workspace = workspace
        self._max_bytes = max_bytes

    @property
    def name(self) -> str:
        return "read_file"

    @property
    def description(self) -> str:
        return (
            "Read a UTF-8 text file from the workspace. "
            "The path must be workspace-relative."
        )

    @property
    def input_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Workspace-relative file path.",
                },
            },
            "required": ["path"],
            "additionalProperties": False,
        }

    def run(self, arguments: dict[str, Any]) -> dict[str, Any]:
        path = arguments["path"]
        file_path = self._workspace.resolve(path)

        if not file_path.exists():
            raise FileNotFoundError(
                f"File not found: {path}"
            )

        if not file_path.is_file():
            raise IsADirectoryError(
                f"Path is not a file: {path}"
            )

        size = file_path.stat().st_size

        if size > self._max_bytes:
            raise ValueError(
                f"File is too large to read: "
                f"{path} ({size} bytes, "
                f"limit {self._max_bytes})"
            )

        try:
            content = file_path.read_text(
                encoding="utf-8"
            )
        except UnicodeDecodeError as exc:
            raise ValueError(
                f"File is not valid UTF-8 text: {path}"
            ) from exc

        return {
            "path": path,
            "content": content,
            "size_bytes": size,
        }
```

### 20. `app/tools/search_text.py` — SearchText Tool 🆕

**ဘာလုပ်သလဲ:** Workspace အတွင်းရှိ files များထဲတွင် case-insensitive text search ပြုလုပ်ပေးပြီး matching line numbers နှင့် text များကို ပြန်ပေးသော tool ဖြစ်သည်။ Cognitive Complexity ≤ 15 စံနှုန်းနှင့်အညီ `_search_file()` helper သို့ clean refactoring ပြုလုပ်ထားပြီး `.git` directory များကို automatically skip လုပ်သည်။

| Method / Helper | တာဝန် |
|---|---|
| `__init__(workspace, *, max_results, max_file_bytes)` | `max_results` (default: 50) နှင့် `max_file_bytes` (default: 200,000) limits သတ်မှတ်သည်။ |
| `run(arguments)` | Query နှင့် path ကို စစ်ဆေးသည် → target files များကို iterate လုပ်သည် → line matches များကို စုဆောင်းပြီး `max_results` ပြည့်ပါက ရပ်တန့်သည်။ |
| `_search_file(file_path, relative_path, query)` | ဖိုင်တစ်ခုချင်းစီ၏ UTF-8 lines များကို ဖတ်ပြီး `query_lower in line.lower()` ကို ရှာကာ line number ပါဝင်သော matches list ကို ပြန်ပေးသည်။ |
| `_iter_files(directory)` | Recursive glob ဖြင့် files များကို ရှာဖွေပြီး `.git` directory များကို skip လုပ်သည်။ |

```python
from pathlib import Path
from typing import Any

from .base import Tool
from .workspace import Workspace


class SearchTextTool(Tool):
    """Search for text in workspace files."""

    def __init__(
        self,
        workspace: Workspace,
        *,
        max_results: int = 50,
        max_file_bytes: int = 200_000,
    ) -> None:
        self._workspace = workspace
        self._max_results = max_results
        self._max_file_bytes = max_file_bytes

    @property
    def name(self) -> str:
        return "search_text"

    @property
    def description(self) -> str:
        return (
            "Search for a text string inside workspace files. "
            "Returns matching file paths and line numbers."
        )

    @property
    def input_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Text to search for.",
                },
                "path": {
                    "type": "string",
                    "description": (
                        "Workspace-relative directory or file. "
                        "Use an empty string for the workspace root."
                    ),
                },
            },
            "required": ["query", "path"],
            "additionalProperties": False,
        }

    def run(self, arguments: dict[str, Any]) -> list[dict[str, Any]]:
        query = arguments["query"]
        path = arguments["path"]

        if not query:
            raise ValueError("Search query cannot be empty.")

        target = self._workspace.resolve(path)

        if not target.exists():
            raise FileNotFoundError(
                f"Path does not exist: {path}"
            )

        files = (
            [target]
            if target.is_file()
            else self._iter_files(target)
        )

        results: list[dict[str, Any]] = []

        for file_path in files:
            if len(results) >= self._max_results:
                break

            if file_path.stat().st_size > self._max_file_bytes:
                continue

            relative_path = file_path.relative_to(self._workspace.root)
            matches = self._search_file(file_path, relative_path, query)
            results.extend(matches)

            if len(results) >= self._max_results:
                results = results[: self._max_results]
                break

        return results

    def _search_file(
        self,
        file_path: Path,
        relative_path: Path,
        query: str,
    ) -> list[dict[str, Any]]:
        """Return matching lines from a single file."""
        try:
            lines = file_path.read_text(encoding="utf-8").splitlines()
        except (UnicodeDecodeError, OSError):
            return []

        matches: list[dict[str, Any]] = []
        query_lower = query.lower()

        for line_number, line in enumerate(lines, start=1):
            if query_lower in line.lower():
                matches.append(
                    {
                        "path": relative_path.as_posix(),
                        "line": line_number,
                        "text": line,
                    }
                )

        return matches

    def _iter_files(self, directory: Path) -> list[Path]:
        files: list[Path] = []

        for path in directory.rglob("*"):
            if not path.is_file():
                continue

            if ".git" in path.parts:
                continue

            files.append(path)

        return sorted(files)
```

### 21. `app/tools/registry.py` — Tool Registry

**ဘာလုပ်သလဲ:** Tool များကို နာမည်ဖြင့် register လုပ်ခြင်း၊ ရှာဖွေခြင်း (lookup) နှင့် duplicate registration မဖြစ်စေရန် validate လုပ်ပေးသော centralized store ဖြစ်သည်။

| Method | တာဝန် |
|---|---|
| `register(tool: Tool)` | Tool အား register လုပ်သည်။ နာမည်တူ tool ရှိနှင့်ပြီးပါက `ValueError("Tool already registered: ...")` raise လုပ်သည်။ |
| `get(name: str) -> Tool` | နာမည်ဖြင့် tool ကို ရှာယူသည်။ မရှိပါက `KeyError("Unknown tool: ...")` raise လုပ်သည်။ |
| `list() -> list[Tool]` | Register လုပ်ထားသော tool objects အားလုံးကို list ပြန်ပေးသည်။ |
| `definitions() -> list[dict]` | Registered tools များအားလုံး၏ metadata definitions list ကို ပြန်ပေးသည်။ |

```python
import builtins

from .base import Tool


class ToolRegistry:
    """Stores and resolves tools by name."""

    def __init__(self) -> None:
        self._tools: dict[str, Tool] = {}

    def register(self, tool: Tool) -> None:
        if tool.name in self._tools:
            raise ValueError(
                f"Tool already registered: {tool.name}"
            )

        self._tools[tool.name] = tool

    def get(self, name: str) -> Tool:
        try:
            return self._tools[name]
        except KeyError as exc:
            raise KeyError(
                f"Unknown tool: {name}"
            ) from exc

    def list(self) -> list[Tool]:
        return list(self._tools.values())

    def definitions(self) -> builtins.list[dict]:
        return [
            tool.definition()
            for tool in self._tools.values()
        ]
```

---

## ⚙️ PART 2: CONFIGURATION & DOCUMENTATION FILES
### 22. `pyproject.toml` — Project Configuration & Build Tooling

**ဘာလုပ်သလဲ:** Project ၏ metadata, dependencies, Python version (>=3.11), build system (hatchling), dev dependencies (pytest, mypy, ruff) နှင့် linter settings များကို သတ်မှတ်ထားသော configuration file ဖြစ်သည်။

```toml
[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[project]
name = "agent-runtime"
version = "0.1.0"
description = "Minimal agentic runtime with a pluggable LLM client."
requires-python = ">=3.11"
dependencies = [
    "openai>=1.0",
    "python-dotenv>=1.0",
    "pydantic>=2.0",
]

[project.optional-dependencies]
dev = [
    "pytest>=8.0",
    "pytest-cov",
    "mypy",
    "ruff",
]

[tool.pytest.ini_options]
testpaths = ["tests"]

[tool.ruff]
line-length = 100
```

### 23. `.env.example` — Environment Variable Template

**ဘာလုပ်သလဲ:** OpenAI API key နှင့် configurations များအတွက် template ဖြစ်သည်။ Real values များကို `.env` file သို့ ကူးယူထည့်သွင်းရမည်ဖြစ်ပြီး git ထဲ commit မပြုလုပ်ရပါ။

```text
# Copy this file to .env and fill in your real values.
# Never commit .env to version control.

OPENAI_API_KEY=
OPENAI_MODEL=
OPENAI_TEMPERATURE=
```

### 24. `conftest.py` — Pytest Path Configuration

**ဘာလုပ်သလဲ:** Pytest test runner အား project root directory ကို Python sys.path ထဲသို့ ထည့်သွင်းစေပြီး test files များမှ `from app.xxx import ...` ဟု absolute imports သုံးနိုင်ရန် ပြုလုပ်ပေးသည်။

```python
# conftest.py — project-root conftest
# Placing this file here tells pytest to add the agent-runtime/ directory
# to sys.path so that `from app.xxx import ...` works in all test modules.
```

### 25. `README.md` — Project Overview & Vision

**ဘာလုပ်သလဲ:** Project ၏ ရည်ရွယ်ချက်၊ Third-party frameworks (LangChain, CrewAI စသည်) မပါဘဲ Native LLM SDK ဖြင့် coding agent runtime အား from-scratch တည်ဆောက်ပုံ အနှစ်ချုပ်ကို ဖော်ပြထားသည်။

```markdown
# Agent Runtime

A coding agent runtime built from scratch in Python.

## Goals

This project implements a software engineering agent without:

- LangChain
- LangGraph
- CrewAI
- LlamaIndex

Only an LLM provider SDK is used for model communication.

## Current Provider

OpenAI

## Architecture

```text
Agent Runtime
     |
     v
 LLMClient
     |
     +---- OpenAIClient
     |
     +---- FakeLLMClient
```

### 26. `PROGRESS.md` — Learning Milestones Log

**ဘာလုပ်သလဲ:** Agent runtime တည်ဆောက်ခြင်း သင်ယူမှုခရီးစဉ်၏ Day-by-Day progress logs များကို မှတ်တမ်းတင်ထားသည်။

```markdown
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
```

### 27. `docs/adr/0001-llm-provider-abstraction.md` — ADR-0001: Provider-Independent Interface

**ဘာလုပ်သလဲ:** OpenAI SDK ကို တိုက်ရိုက်မမှီခိုဘဲ Provider-Independent `LLMClient` interface အား မိတ်ဆက်ရခြင်း၏ context, decision, positive/negative consequences များကို မှတ်တမ်းတင်ထားသော Architecture Decision Record ဖြစ်သည်။

```markdown
# ADR-0001: Introduce a Provider-Independent LLM Interface

## Status

Accepted

## Context

The coding agent needs to communicate with an LLM provider.

The initial provider is OpenAI.

However, coupling the agent runtime directly to the OpenAI SDK would
make the core runtime dependent on a specific provider.

The project also needs deterministic tests that do not make real
network calls or consume API credits.

## Decision

Introduce a provider-independent `LLMClient` interface.

The runtime depends on:

    LLMClient

The OpenAI implementation is:

    OpenAIClient

Tests can use:

    FakeLLMClient

The OpenAI SDK is therefore isolated behind the LLM client boundary.

## Consequences

### Positive

- Agent runtime is not coupled directly to OpenAI.
- Tests can be deterministic.
- Provider replacement is easier.
- External API concerns remain isolated.
- Future tool-calling implementation can map provider-specific
  responses into internal runtime models.

### Negative

- Adds a small abstraction layer.
- Provider-specific capabilities may require additional interfaces
  or adapters later.

## Alternatives Considered

### Direct OpenAI SDK usage

Rejected because it couples the runtime to a specific provider.

### Generic third-party agent framework

Rejected because this project explicitly builds the runtime
from scratch for learning and architectural understanding.
```

### 28. `.gitignore` — Git Ignore Rules 🔄

**ဘာလုပ်သလဲ:** Python caches, virtual environments, coverage files, mypy caches နှင့် local learning journey notes များကို version control မှ exclude လုပ်ထားသည်။

```text
# Python
__pycache__/
*.py[cod]
*.pyo
*.pyd
*.egg-info/
dist/
build/
*.egg

# Virtual environments
.venv/
venv/
env/

# Environment secrets
.env

# IDE / editors
.vscode/
.idea/
*.swp

# pytest / coverage
.pytest_cache/
.coverage
htmlcov/

# mypy
.mypy_cache/

# Documentation / Notes
Agentic-AI-Learning-Journey.md
```

---

## 🧪 PART 3: COMPLETE TEST SUITE (`tests/`) — ALL 37 TESTS

> Test suite တစ်ခုလုံးတွင် Unit tests, Integration tests နှင့် Multi-step Error Recovery experiments များ စုစုပေါင်း **37 ခု** ပါဝင်ပြီး အားလုံး **100% PASSING** ဖြစ်သည်။
### 29. `tests/test_tools.py` — Tool & Registry Unit Tests (7 tests) 🔄

**ဘာလုပ်သလဲ:** `ListFilesTool` နှင့် `ToolRegistry` တို့၏ အခြေခံ features များကို စစ်ဆေးသော tests ဖြစ်သည်။ `ListFilesTool(Workspace(Path.cwd()))` ဖြင့် workspace-aware အဖြစ် update လုပ်ထားသည်။

| Test Function | စစ်ဆေးချက် |
|---|---|
| `test_list_files_tool_lists_directory` | Directory အတွင်းရှိ files များကို list အဖြစ် ပြန်ပေးခြင်း |
| `test_list_files_tool_definition` | Tool metadata definition (name, description, schema) မှန်ကန်ခြင်း |
| `test_registry_registers_and_resolves_tool` | Tool register လုပ်ခြင်းနှင့် name ဖြင့် ပြန်လည်ရယူခြင်း |
| `test_registry_exposes_tool_definitions` | Definitions list ထုတ်ပေးနိုင်ခြင်း |
| `test_registry_rejects_duplicate_tool` | နာမည်တူ tool ထပ် register လုပ်ပါက ValueError တက်ခြင်း |
| `test_registry_rejects_unknown_tool` | မရှိသော tool ကို get လုပ်ပါက KeyError တက်ခြင်း |
| `test_tool_call_representation` | `ToolCall` dataclass ၏ attributes များ မှန်ကန်ခြင်း |

```python
from pathlib import Path

from app.tools import ListFilesTool, ToolRegistry, Workspace


def test_list_files_tool_lists_directory() -> None:
    tool = ListFilesTool(Workspace(Path.cwd()))

    result = tool.run({"path": "."})

    assert isinstance(result, list)
    assert "app" in result
    assert "tests" in result


def test_list_files_tool_definition() -> None:
    tool = ListFilesTool(Workspace(Path.cwd()))

    definition = tool.definition()

    assert definition["name"] == "list_files"
    assert "description" in definition
    assert definition["input_schema"]["type"] == "object"


def test_registry_registers_and_resolves_tool() -> None:
    registry = ToolRegistry()
    tool = ListFilesTool(Workspace(Path.cwd()))

    registry.register(tool)

    resolved = registry.get("list_files")

    assert resolved is tool


def test_registry_exposes_tool_definitions() -> None:
    registry = ToolRegistry()

    registry.register(ListFilesTool(Workspace(Path.cwd())))

    definitions = registry.definitions()

    assert len(definitions) == 1
    assert definitions[0]["name"] == "list_files"


def test_registry_rejects_duplicate_tool() -> None:
    registry = ToolRegistry()

    registry.register(ListFilesTool(Workspace(Path.cwd())))

    try:
        registry.register(ListFilesTool(Workspace(Path.cwd())))
    except ValueError as exc:
        assert "already registered" in str(exc)
    else:
        raise AssertionError(
            "Expected duplicate registration to fail"
        )


def test_registry_rejects_unknown_tool() -> None:
    registry = ToolRegistry()

    try:
        registry.get("does_not_exist")
    except KeyError as exc:
        assert "Unknown tool" in str(exc)
    else:
        raise AssertionError(
            "Expected unknown tool lookup to fail"
        )


def test_tool_call_representation() -> None:
    from app.tools.call import ToolCall

    call = ToolCall(
        call_id="call_123",
        tool_name="list_files",
        arguments={"path": "src"},
    )

    assert call.call_id == "call_123"
    assert call.tool_name == "list_files"
    assert call.arguments == {
        "path": "src"
    }
```

### 30. `tests/test_llm_client.py` — Fake LLM Client Unit Tests (2 tests)

**ဘာလုပ်သလဲ:** `FakeLLMClient` ၏ basic ask response ပြန်ပေးခြင်းနှင့် prompt logging စနစ်များကို စစ်ဆေးသည်။

| Test Function | စစ်ဆေးချက် |
|---|---|
| `test_fake_llm_returns_configured_response` | Configured response စာသားအတိုင်း ပြန်လည်ရရှိခြင်း |
| `test_fake_llm_records_prompt` | ပေးပို့လိုက်သော system prompt နှင့် user prompt များကို calls list တွင် မှတ်တမ်းတင်ထားခြင်း |

```python
from app.llm import FakeLLMClient


def test_fake_llm_returns_configured_response() -> None:
    llm = FakeLLMClient(
        response="Hello from fake LLM",
    )

    result = llm.ask(
        system_prompt="You are a test assistant.",
        user_prompt="Say hello.",
    )

    assert result == "Hello from fake LLM"


def test_fake_llm_records_prompt() -> None:
    llm = FakeLLMClient(
        response="test response",
    )

    llm.ask(
        system_prompt="system instruction",
        user_prompt="user request",
    )

    assert len(llm.calls) == 1

    assert llm.calls[0] == {
        "system_prompt": "system instruction",
        "user_prompt": "user request",
    }
```

### 31. `tests/test_openai_tools.py` — OpenAI Tool Schema Conversion Test (1 test) 🔄

**ဘာလုပ်သလဲ:** `to_openai_tool()` adapter function သည် `Workspace`-aware tool object အား OpenAI specification သို့ မှန်ကန်စွာ convert လုပ်နိုင်ခြင်း ရှိမရှိ စစ်ဆေးသည်။

```python
from pathlib import Path

from app.llm.openai_tools import to_openai_tool
from app.tools.list_files import ListFilesTool
from app.tools.workspace import Workspace


def test_tool_is_converted_to_openai_function() -> None:
    tool = ListFilesTool(Workspace(Path.cwd()))

    result = to_openai_tool(tool)

    assert result["type"] == "function"
    assert result["name"] == "list_files"
    assert result["description"] == tool.description
    assert result["parameters"] == tool.input_schema
    assert result["strict"] is True
```

### 32. `tests/test_single_iteration.py` — Single Iteration Loop Tests (2 tests) 🔄

**ဘာလုပ်သလဲ:** Day 3 Single iteration loop ၏ အလုပ်လုပ်ပုံကို စစ်ဆေးသည်။ Tool call မလိုသော prompt နှင့် tool call လိုအပ်သော prompt နှစ်မျိုးစလုံးကို fake LLM ဖြင့် စမ်းသပ်ထားသည်။

```python
from pathlib import Path
from types import SimpleNamespace

from app.agent.single_iteration import run_single_iteration
from app.llm.fake_client import FakeLLMClient, FakeResponse
from app.tools.executor import ToolExecutor
from app.tools.list_files import ListFilesTool
from app.tools.registry import ToolRegistry
from app.tools.workspace import Workspace


def test_single_iteration_with_no_tool_calls_returns_response() -> None:
    """When the model returns no tool calls, the response is returned directly."""
    registry = ToolRegistry()
    executor = ToolExecutor(registry)

    fake_llm = FakeLLMClient(response="No tools needed.")

    result = run_single_iteration(
        client=fake_llm,
        executor=executor,
        tools=registry.list(),
        user_prompt="Hello.",
    )

    assert result.output_text == "No tools needed."
    assert len(fake_llm.calls) == 1
    assert fake_llm.calls[0]["user_prompt"] == "Hello."


def test_single_iteration_executes_tool_and_returns_final_response() -> None:
    registry = ToolRegistry()
    registry.register(ListFilesTool(Workspace(Path.cwd())))

    executor = ToolExecutor(registry)

    fake_llm = FakeLLMClient(
        response="The workspace contains an app directory.",
        first_response=FakeResponse(
            output_text="",
            output=[
                SimpleNamespace(
                    type="function_call",
                    call_id="call_123",
                    name="list_files",
                    arguments='{"path": "."}',
                )
            ],
        ),
    )

    result = run_single_iteration(
        client=fake_llm,
        executor=executor,
        tools=registry.list(),
        user_prompt="Inspect the workspace.",
    )

    assert result.output_text == (
        "Final response after tool execution."
    )

    assert len(fake_llm.calls) == 2

    assert fake_llm.calls[0]["tools"] == [
        "list_files"
    ]

    conversation = fake_llm.calls[1]["conversation"]

    assert conversation[0] == {
        "role": "user",
        "content": "Inspect the workspace.",
    }

    assert conversation[1].type == "function_call"
    assert conversation[1].call_id == "call_123"

    assert conversation[2]["type"] == "function_call_output"
    assert conversation[2]["call_id"] == "call_123"
```

### 33. `tests/test_agent_state.py` — Agent State Machine Tests (4 tests) 🆕

**ဘာလုပ်သလဲ:** `AgentState` ၏ default values, `COMPLETED`, `FAILED`, `MAX_ITERATIONS` states များနှင့် `is_finished` property ၏ exit condition logic များကို စစ်ဆေးသည်။

| Test Function | စစ်ဆေးချက် |
|---|---|
| `test_agent_state_defaults` | Default state တွင် status = RUNNING, iteration = 0, is_finished = False ဖြစ်ခြင်း |
| `test_agent_state_completed` | Status = COMPLETED ဖြစ်ပါက is_finished = True ဖြစ်ခြင်း |
| `test_agent_state_failed` | Status = FAILED ဖြစ်ပါက error message ပါရှိပြီး is_finished = True ဖြစ်ခြင်း |
| `test_agent_state_max_iterations` | Status = MAX_ITERATIONS ဖြစ်ပါက is_finished = True ဖြစ်ခြင်း |

```python
from app.agent import AgentState, AgentStatus


def test_agent_state_defaults():
    state = AgentState()

    assert state.conversation == []
    assert state.iteration == 0
    assert state.status == AgentStatus.RUNNING
    assert state.final_response is None
    assert state.error is None
    assert state.is_finished is False


def test_agent_state_completed():
    state = AgentState(
        status=AgentStatus.COMPLETED,
        final_response="Done.",
    )

    assert state.is_finished is True
    assert state.final_response == "Done."


def test_agent_state_failed():
    state = AgentState(
        status=AgentStatus.FAILED,
        error="Tool execution failed.",
    )

    assert state.is_finished is True
    assert state.error == "Tool execution failed."


def test_agent_state_max_iterations():
    state = AgentState(
        status=AgentStatus.MAX_ITERATIONS,
        iteration=5,
    )

    assert state.is_finished is True
    assert state.iteration == 5
```

### 34. `tests/test_agent_loop.py` — Multi-Iteration Agent Loop Tests (4 tests) 🔄

**ဘာလုပ်သလဲ:** Multi-turn `AgentLoop` ၏ orchestration logic ကို စစ်ဆေးသည်။ `_make_loop()` helper တွင် `Workspace`, `ListFilesTool`, `ReadFileTool`, `SearchTextTool` ၃ ခုစလုံး ပါဝင်အောင် update ပြုလုပ်ထားသည်။

| Test Function | စစ်ဆေးချက် |
|---|---|
| `test_agent_loop_completes_after_tool_call` | Iteration 0 တွင် tool call → Iteration 1 တွင် final answer ရရှိကာ COMPLETED ဖြစ်ခြင်း |
| `test_agent_loop_stops_at_max_iterations` | အမြဲတမ်း tool call ခေါ်နေပါက max_iterations တွင် infinite loop မဖြစ်ဘဲ ရပ်တန့်ခြင်း |
| `test_agent_loop_preserves_conversation` | User prompt, function_call, function_call_output message flow အပြည့်အစုံ conversation ထဲတွင် ရှိနေခြင်း |
| `test_agent_loop_records_tool_execution` | Tool execution တိုင်းကို `state.history` ထဲသို့ `ExecutionRecord` အဖြစ် duration ပါ မှတ်တမ်းတင်ခြင်း |

```python
from pathlib import Path
from types import SimpleNamespace

from app.agent import AgentLoop, AgentStatus
from app.llm import FakeLLMClient, FakeResponse
from app.tools import (
    ListFilesTool,
    ReadFileTool,
    SearchTextTool,
    ToolExecutor,
    ToolRegistry,
    Workspace,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_function_call_item(
    *,
    call_id: str,
    name: str,
    arguments: str,
) -> SimpleNamespace:
    """Build a fake LLM output item that looks like a function_call."""
    return SimpleNamespace(
        type="function_call",
        call_id=call_id,
        name=name,
        arguments=arguments,
    )


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
    assert "Final answer" in state.final_response
    assert state.iteration == 1      # incremented after iteration 0 only

    # LLM was called exactly twice
    respond_calls = [
        c for c in fake_llm.calls if c.get("method") == "respond_with_tools"
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
    assert conv[0] == {"role": "user", "content": "Inspect workspace."}

    # [1] function_call item appended from response.output
    assert conv[1].type == "function_call"
    assert conv[1].call_id == "call_abc"
    assert conv[1].name == "list_files"

    # [2] tool execution result
    assert conv[2]["type"] == "function_call_output"
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
```

### 35. `tests/test_workspace.py` — Workspace Security Boundary Tests (3 tests) 🆕

**ဘာလုပ်သလဲ:** `Workspace` ၏ path resolution နှင့် Path Traversal attack (`../../secret.txt`) တားဆီးမှုများကို စစ်ဆေးသည်။

| Test Function | စစ်ဆေးချက် |
|---|---|
| `test_workspace_resolves_relative_path` | Workspace relative path ကို root အောက်တွင် မှန်ကန်စွာ resolve လုပ်ခြင်း |
| `test_workspace_allows_nested_path` | Subdirectories အဆင့်ဆင့်ပါသော nested path များကို ခွင့်ပြုခြင်း |
| `test_workspace_blocks_path_traversal` | Workspace root ပြင်ပသို့ ထွက်သော `../../secret.txt` ကို `PermissionError` ဖြင့် block လုပ်ခြင်း |

```python
from pathlib import Path

import pytest

from app.tools import Workspace


def test_workspace_resolves_relative_path(
    tmp_path: Path,
) -> None:
    workspace = Workspace(tmp_path)

    resolved = workspace.resolve(
        "src"
    )

    assert resolved == (
        tmp_path / "src"
    ).resolve()


def test_workspace_allows_nested_path(
    tmp_path: Path,
) -> None:
    workspace = Workspace(tmp_path)

    resolved = workspace.resolve(
        "src/app/main.py"
    )

    assert resolved == (
        tmp_path / "src/app/main.py"
    ).resolve()


def test_workspace_blocks_path_traversal(
    tmp_path: Path,
) -> None:
    workspace = Workspace(tmp_path)

    with pytest.raises(
        PermissionError,
        match="escapes workspace",
    ):
        workspace.resolve(
            "../../secret.txt"
        )
```

### 36. `tests/test_file_tools.py` — File Tools Integration Tests (4 tests) 🆕

**ဘာလုပ်သလဲ:** `ListFilesTool`, `ReadFileTool`, `SearchTextTool` ၃ ခုစလုံး၏ workspace-aware integration အလုပ်လုပ်ပုံကို စစ်ဆေးသည်။

| Test Function | စစ်ဆေးချက် |
|---|---|
| `test_list_files_uses_workspace` | Workspace-relative path မှ files များကို list လုပ်ပေးခြင်း |
| `test_read_file_returns_content` | ဖိုင် content, path နှင့် size_bytes များကို မှန်ကန်စွာ ဖတ်ရှုပေးခြင်း |
| `test_read_file_rejects_large_file` | သတ်မှတ်ထားသော `max_bytes` ထက်ကျော်လွန်ပါက `ValueError` ဖြင့် ငြင်းပယ်ခြင်း |
| `test_search_text_returns_matches` | Text pattern ကို ရှာဖွေပြီး matching file path, line number, line text ပြန်ပေးခြင်း |

```python
from pathlib import Path

import pytest

from app.tools import (
    ListFilesTool,
    ReadFileTool,
    SearchTextTool,
    Workspace,
)


def test_list_files_uses_workspace(
    tmp_path: Path,
) -> None:
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "main.py").write_text(
        "print('hello')",
        encoding="utf-8",
    )

    workspace = Workspace(tmp_path)
    tool = ListFilesTool(workspace)

    result = tool.run(
        {"path": "src"}
    )

    assert result == ["main.py"]


def test_read_file_returns_content(
    tmp_path: Path,
) -> None:
    file_path = (
        tmp_path / "main.py"
    )

    file_path.write_text(
        "print('hello')\n",
        encoding="utf-8",
    )

    workspace = Workspace(tmp_path)
    tool = ReadFileTool(workspace)

    result = tool.run(
        {"path": "main.py"}
    )

    assert result["path"] == "main.py"
    assert result["content"] == (
        "print('hello')\n"
    )


def test_read_file_rejects_large_file(
    tmp_path: Path,
) -> None:
    file_path = (
        tmp_path / "large.txt"
    )

    file_path.write_text(
        "x" * 20,
        encoding="utf-8",
    )

    workspace = Workspace(tmp_path)
    tool = ReadFileTool(
        workspace,
        max_bytes=10,
    )

    with pytest.raises(
        ValueError,
        match="too large",
    ):
        tool.run(
            {"path": "large.txt"}
        )


def test_search_text_returns_matches(
    tmp_path: Path,
) -> None:
    src = tmp_path / "src"
    src.mkdir()

    (src / "auth.py").write_text(
        "def login():\n"
        "    return True\n",
        encoding="utf-8",
    )

    (src / "user.py").write_text(
        "class User:\n"
        "    pass\n",
        encoding="utf-8",
    )

    workspace = Workspace(tmp_path)
    tool = SearchTextTool(workspace)

    result = tool.run(
        {
            "query": "login",
            "path": "src",
        }
    )

    assert result == [
        {
            "path": "src/auth.py",
            "line": 1,
            "text": "def login():",
        }
    ]
```

### 37. `tests/test_error_recovery.py` — Day 5 Error Recovery & Security Experiments (13 tests) 🆕

**ဘာလုပ်သလဲ:** Agentic AI စနစ်၏ အဓိက experiment ၅ ခုဖြစ်သော Tool Error Recovery, Path Traversal Block, Huge Output Context Budgeting, Realistic Exploration Smoke Test နှင့် Max Iterations Protection တို့ကို စစ်ဆေးသော tests ၁၃ ခု ဖြစ်သည်။

| Experiment Class | Test Function | အဓိက စစ်ဆေးချက် |
|---|---|---|
| **Exp 1: Tool Error Recovery** | `test_agent_continues_after_tool_error` | မရှိသော file ဖတ်မိ၍ tool error တက်သော်လည်း agent crash မဖြစ်ဘဲ recover လုပ်နိုင်ခြင်း |
| | `test_failed_tool_recorded_in_history` | ကျရှုံးသော tool call ကို `history.records()[0].success is False` ဟု မှတ်တမ်းတင်ခြင်း |
| | `test_error_observation_appended_to_conversation` | Error message သည် observation အနေဖြင့် LLM ဆီသို့ function_call_output ရောက်ရှိသွားခြင်း |
| | `test_hallucinated_tool_name_recovery` | မရှိသော tool နာမည် (e.g. repo_browser.list_files) ခေါ်မိသော်လည်း error observation ရရှိပြီး valid tool သို့ self-correct လုပ်နိုင်ခြင်း |
| | `test_invalid_file_recovery` | Tool name မှန်သော်လည်း argument/path မှားယွင်းခြင်း (`missing.py`) ကို recover လုပ်၍ `list_files` ဖြင့် ရှာဖွေနိုင်ခြင်း |
| **Exp 2: Path Traversal** | `test_path_traversal_blocked_and_agent_survives` | `../../secret.txt` ခေါ်သော်လည်း agent process ရှင်သန်ပြီး COMPLETED ဖြစ်ခြင်း |
| | `test_path_traversal_recorded_as_failure` | History တွင် `"escapes workspace"` error ဖြင့် failure အဖြစ် မှတ်တမ်းတင်ခြင်း |
| | `test_path_traversal_error_forwarded_to_llm` | PermissionError ကို LLM ထံ observation အဖြစ် ပို့ဆောင်ပေးခြင်း |
| **Exp 3: Huge Output** | `test_oversized_file_produces_tool_failure` | `max_bytes` ကျော်သောဖိုင်ကို ဖတ်ရာတွင် tool failure အဖြစ် သတ်မှတ်ခြင်း |
| | `test_oversized_file_error_forwarded_to_llm` | Context budget error observation အား LLM ထံ ပြန်ပို့ခြင်း |
| **Exp 4: Realistic Exploration** | `test_realistic_exploration_sequence` | `list_files` → `read_file` → final answer အဆင့်ဆင့် exploration အောင်မြင်ခြင်း |
| | `test_history_json_is_serialisable` | `state.history.to_json()` သည် valid JSON ထုတ်ပေးပြီး duration_ms ပါဝင်ခြင်း |
| **Exp 5: Max Iterations Protection** | `test_max_iterations_stops_infinite_tool_loop` | Model က အဆုံးမရှိ loop ဖြစ်နေပါက max_iterations (e.g. 3) တွင် `MAX_ITERATIONS` status ဖြင့် safely ရပ်တန့်ခြင်း |

```python
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

        second_call_conv = fake_llm.calls[1]["conversation"]
        tool_outputs = [
            m for m in second_call_conv
            if isinstance(m, dict) and m.get("type") == "function_call_output"
        ]

        assert len(tool_outputs) == 1
        assert tool_outputs[0]["call_id"] == "call_err"

        payload = json.loads(tool_outputs[0]["output"])
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
        second_conv = fake_llm.calls[1]["conversation"]
        tool_outputs = [
            m
            for m in second_conv
            if isinstance(m, dict) and m.get("type") == "function_call_output"
        ]
        assert len(tool_outputs) == 1
        payload = json.loads(tool_outputs[0]["output"])
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

        second_conv = fake_llm.calls[1]["conversation"]
        tool_outputs = [
            m for m in second_conv
            if isinstance(m, dict) and m.get("type") == "function_call_output"
        ]

        assert len(tool_outputs) == 1
        payload = json.loads(tool_outputs[0]["output"])
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

        second_conv = fake_llm.calls[1]["conversation"]
        tool_outputs = [
            m for m in second_conv
            if isinstance(m, dict) and m.get("type") == "function_call_output"
        ]

        payload = json.loads(tool_outputs[0]["output"])
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
```

---

## 🔬 ERROR RECOVERY TAXONOMY & CONTEXT ENGINEERING

### Recovery Failure Types (မတူညီသော Error အမျိုးအစား ၂ မျိုး)
1. **Experiment 1A (Wrong Tool / Hallucinated Tool Name):**
   - ဥပမာ: `repo_browser.list_files`
   - Failure: `ToolRegistry.get()` မှ `KeyError` တက်သည်။
   - Recovery: Tool name ကို registry ထဲရှိ valid tool နာမည်အဖြစ် ပြောင်းလဲခေါ်ဆိုသည်။
2. **Experiment 1B (Correct Tool, Wrong Input / Invalid Path):**
   - ဥပမာ: `read_file("missing.py")`
   - Failure: `ReadFileTool.run()` မှ `FileNotFoundError` တက်သည်။
   - Recovery: Path အမှားကို နားလည်ပြီး `list_files(".")` ဖြင့် directory ကို အရင်စူးစမ်းကာ မှန်ကန်သော ဖိုင်လမ်းကြောင်းကို ရှာဖွေသည်။

### Context Engineering Preview
> **အဓိက သဘောတရား:** `read_file` failure ဖြစ်ချိန်တွင် `AgentLoop` က "File မတွေ့ဘူး → `list_files` သုံးလိုက်" ဟု ဘယ်တော့မှ မဆုံးဖြတ်ပါ။ `AgentLoop` သည် `error → observation → conversation` သို့ သယ်ဆောင်ပေးရုံသာ လုပ်သည်။ ထို observation ကို ဖတ်ရှုပြီး **Re-plan လုပ်ကာ `list_files` ကို ရွေးချယ်သူမှာ LLM သာ ဖြစ်သည်**။
> ထို့ကြောင့် *"Conversation ထဲတွင် မည်သည့် context နှင့် observation format မျိုး ထည့်သွင်းပေးထားလျှင် LLM က အမှားကို အကောင်းဆုံး recover လုပ်နိုင်မည်နည်း?"* ဆိုသည့် မေးခွန်းသည် **Context Engineering** ၏ အခြေခံအုတ်မြစ် ဖြစ်သည်။

---

## 🛑 RUNTIME SAFETY & LIFECYCLE REASONING

### Key Conceptual Distinctions
- **Tool Failure ≠ Agent Failure**: Tool တစ်ခု error တက်ခြင်းသည် Agent run ပျက်စီးခြင်း မဟုတ်ပါ။ အမှန်စင်စစ် LLM အတွက် observation အသစ်ရရှိခြင်း ဖြစ်သည်။
- **Max Iteration ≠ Tool Failure**: Tool execution အားလုံးသည် `success=True` ဖြစ်နိုင်သော်လည်း (ဥပမာ `list_files` ကို အကြိမ်ကြိမ် အောင်မြင်စွာ run နေသော်လည်း) LLM က final answer မပေးပါက `max_iterations` guard ကြောင့် loop ရပ်တန့်သွားသည်။ ဤအခြေအနေတွင် agent status သည် `FAILED` မဟုတ်ဘဲ `MAX_ITERATIONS` ဖြစ်သည်။

### AgentStatus Runtime Lifecycle

```
                 ┌────────────┐
                 │   RUNNING  │
                 └─────┬──────┘
                       │
             ┌─────────┼──────────┐
             │         │          │
             ▼         ▼          ▼
        COMPLETED   MAX_ITER    FAILED
```

| Status | အဓိပ္ပာယ် | ဖြစ်ပေါ်သည့် အကြောင်းရင်း |
|---|---|---|
| `RUNNING` | Agent loop အလုပ်လုပ်နေဆဲ | Loop iteration မပြီးဆုံးသေးမီ default state |
| `COMPLETED` | Agent အောင်မြင်စွာ ပြီးဆုံး | LLM က tool call မလုပ်တော့ဘဲ final answer text ပြန်ပေးချိန် |
| `MAX_ITERATIONS` | Runtime safety limit ရောက်ရှိ | LLM က final answer မပေးဘဲ tool များကို အဆုံးမရှိ ခေါ်နေသဖြင့် `state.iteration >= max_iterations` ဖြင့် ရပ်တန့်ချိန် |
| `FAILED` | Runtime-level unrecoverable failure | Tool အဆင့်မဟုတ်ဘဲ runtime အဆင့်တွင် unhandled critical exception ဖြစ်ပေါ်ချိန် |

---

## 🔑 KEY DESIGN PATTERNS (ဒီ Codebase တွင် အသုံးပြုထားသော Patterns)

| Pattern | Codebase အသုံးချမှု | အကျိုးကျေးဇူး |
|---|---|---|
| **Abstract Base Class (ABC)** | `LLMClient`, `Tool` | Provider သို့မဟုတ် Tool အသစ်များကို standard interface အတိုင်း အလွယ်တကူ swap ပြုလုပ်နိုင်ခြင်း |
| **Protocol (Duck Typing)** | `ToolCallingClient` | Provider independence (ADR-0001) အရ runtime အား OpenAI SDK နှင့် တိုက်ရိုက်မချိတ်ဆက်စေခြင်း |
| **Dependency Injection** | `ToolExecutor(registry)`, `AgentLoop(client, registry, executor)` | Unit testing တွင် fake dependencies များဖြင့် swap လုပ်ရ လွယ်ကူစေခြင်း |
| **Frozen Dataclass** | `ToolCall`, `ToolExecution`, `ExecutionRecord` | Runtime အချက်အလက်များ မတော်တဆ ပြင်ဆင်မခံရစေရန် Immutability အာမခံခြင်း |
| **Security Boundary Pattern** | `Workspace` | Path traversal attacks များကို tool တိုင်းတွင် duplicate မစစ်ဘဲ single boundary ဖြင့် ဗဟိုချုပ်ကိုင်ခြင်း |
| **Error as Observation** | `ToolExecutor` + `AgentLoop` | Exception ကြောင့် agent မသေစေဘဲ failure အား observation အဖြစ် LLM ထံ ပြန်ပို့၍ self-heal စေခြင်း |
| **Runtime Telemetry** | `ExecutionHistory` + `ExecutionRecord` | Tool execution ကြာချိန် (ms)၊ arguments နှင့် results များကို JSON serialize လုပ်၍ audit log ထားရှိနိုင်ခြင်း |
| **Deterministic Simulation** | `FakeLLMClient.response_sequence` | Network latency သို့မဟုတ် API cost မရှိဘဲ multi-step agent flow များကို deterministically test နိုင်ခြင်း |

---

## 📈 COMPLETE TEST SUITE VERIFICATION (40/40 PASSING)

```
============================= test session starts =============================
platform win32 -- Python 3.12.x, pytest-9.x.x
rootdir: c:\Users\uaung\aung_sann_phyo\person\agentic-ai-learning\agent-runtime
configfile: pyproject.toml
testpaths: tests

tests/test_agent_loop.py ....                                            [ 10%]
tests/test_agent_state.py ....                                           [ 20%]
tests/test_error_recovery.py .............                               [ 52%]
tests/test_file_tools.py ....                                            [ 62%]
tests/test_llm_client.py ..                                              [ 67%]
tests/test_openai_tools.py .                                             [ 70%]
tests/test_single_iteration.py ..                                        [ 75%]
tests/test_tools.py .......                                              [ 92%]
tests/test_workspace.py ...                                              [100%]

============================== 40 passed in 1.69s =============================
```

---

## 🚀 LIVE AGENT RUN TRACE (`python -m app.main`)

Real model (Groq `openai/gpt-oss-120b`) ဖြင့် live run စမ်းသပ်မှုတွင် model သည် **6 tool calls** ပြုလုပ်ခဲ့ပြီး self-correction ပြုလုပ်နိုင်ခဲ့သည်:

```
[Tool 1] list_files("")                          → ✅ workspace root listing
[Tool 2] list_files("app")                       → ✅ app directory listing
[Tool 3] repo_browser.list_files("app/agent")   → ❌ Hallucinated tool name (Error observation)
[Tool 4] list_files("app/agent")                → ✅ Self-corrected immediately!
[Tool 5] read_file("app/main.py")               → ✅ File content read
[Tool 6] read_file("app/agent/loop.py")         → ✅ Found AgentLoop class
```

> **Observation:** Tool Call 3 တွင် model သည် hallucinate ဖြစ်ပြီး မရှိသော tool နာမည် ခေါ်ဆိုခဲ့သော်လည်း Runtime မှ Error Observation ပြန်ပေးလိုက်သည့်အတွက် Call 4 တွင် ချက်ချင်း အမှားပြင်ဆင်ပြီး (Self-heal) အလုပ်ဆက်လုပ်နိုင်ခဲ့သည်။

---

*Updated by Antigravity AI — Agent Runtime Complete Codebase Dump (37 Files, 40 Tests)*
