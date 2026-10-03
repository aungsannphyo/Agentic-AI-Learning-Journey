# Agent Runtime — Complete Codebase Explanation & Code Dump
> ChatGPT သို့မဟုတ် အခြား LLM များသို့ တစ်ခုလုံး paste လုပ်၍ မေးမြန်းလေ့လာနိုင်ရန် project တစ်ခုလုံးရှိ source code, tests, configuration နှင့် architecture explanation များကို single-file အဖြစ် စုစည်းထားသည်။

---

## 🗂️ Complete Project Structure (Week 2 Day 2 Updated)

```
agent-runtime/
├── app/
│   ├── __init__.py                  ← Package marker
│   ├── main.py                      ← 🔄 Entry point (AgentLoop + Workspace + 3 Tools + History JSON)
│   ├── agent/
│   │   ├── __init__.py              ← 🔄 Agent module exports (AgentLoop, AgentState, Decision, StructuredOutput, ValidationErrors)
│   │   ├── decision.py              ← 🆕 Machine-verifiable Decision contract (DecisionAction, Decision Pydantic model)
│   │   ├── decision_schema.py       ← 🆕 JSON Schema generator for Decision (decision_json_schema)
│   │   ├── history.py               ← Telemetry & Execution audit log (ExecutionRecord, ExecutionHistory)
│   │   ├── loop.py                  ← Multi-iteration Orchestrator (ToolCallingClient Protocol, Error as Observation)
│   │   ├── single_iteration.py      ← Day 3 Single iteration loop (foundation)
│   │   ├── state.py                 ← Agent state machine (AgentState, AgentStatus, history tracking)
│   │   ├── structured_output.py     ← 🆕 Structured output strategies (parse_prompt_json, validate_structured_payload)
│   │   └── validation_errors.py     ← 🆕 Pydantic ValidationError formatter for LLM observations
│   ├── llm/
│   │   ├── __init__.py              ← LLM module exports
│   │   ├── client.py                ← Abstract base interface (LLMClient)
│   │   ├── fake_client.py           ← Deterministic test LLM (respond_with_tools, response_sequence)
│   │   ├── openai_client.py         ← Real OpenAI/Groq implementation (respond_with_tools, function calling)
│   │   └── openai_tools.py          ← Tool to OpenAI schema adapter (to_openai_tool)
│   └── tools/
│       ├── __init__.py              ← 🔄 Tools module exports (All 3 tools, Workspace, Executor, Registry, Schemas)
│       ├── argument_registry.py     ← 🆕 Tool Argument Registry (maps tool_name → Pydantic ToolArgs schema)
│       ├── base.py                  ← Abstract Tool base class (name, description, schema, run)
│       ├── call.py                  ← ToolCall data model
│       ├── execution.py             ← ToolExecution data model (with duration_ms and success property)
│       ├── executor.py              ← Tool runner (execution timing & exception boundary)
│       ├── list_files.py            ← Workspace-aware directory listing tool
│       ├── read_file.py             ← Workspace-aware UTF-8 file reader with max_bytes limit
│       ├── registry.py              ← Tool lookup registry (named registry with validation)
│       ├── schemas.py               ← 🆕 Pydantic argument schemas (ToolArgs, ListFilesArgs, ReadFileArgs, SearchTextArgs)
│       ├── search_text.py           ← Text search tool (case-insensitive, Cognitive Complexity <= 15)
│       └── workspace.py             ← Security boundary (path traversal defense)
├── tests/
│   ├── test_agent_loop.py           ← Multi-iteration loop tests (Workspace-aware, 4 tests)
│   ├── test_agent_state.py          ← AgentState & status unit tests (4 tests)
│   ├── test_decision.py             ← 🆕 Decision schema & validation tests (9 tests)
│   ├── test_error_recovery.py       ← Day 5 Experiments (Error Recovery, Path Traversal, Huge Output, Smoke Test - 13 tests)
│   ├── test_file_tools.py           ← Integration tests for Workspace file tools (4 tests)
│   ├── test_llm_client.py           ← Fake LLM unit tests (2 tests)
│   ├── test_openai_tools.py         ← OpenAI tool conversion test (Workspace-aware, 1 test)
│   ├── test_single_iteration.py     ← Single iteration loop tests (Workspace-aware, 2 tests)
│   ├── test_structured_output.py    ← 🆕 Structured output parsing & validation tests (6 tests)
│   ├── test_tools.py                ← Tool & Registry unit tests (Workspace-aware, 7 tests)
│   ├── test_tools_schemas.py        ← 🆕 Pydantic tool argument schema validation tests (11 tests)
│   ├── test_validation_errors.py    ← 🆕 Structured validation error observation tests (1 test)
│   └── test_workspace.py            ← Workspace path resolution & security tests (3 tests)
├── docs/
│   └── adr/
│       └── 0001-llm-provider-abstraction.md ← Architectural Decision Record (Provider Independence)
├── conftest.py                      ← Pytest path configuration
├── pyproject.toml                   ← Build & dependencies (Hatchling, OpenAI, Pydantic, Pytest, Ruff)
├── .env.example                     ← Environment variable template
├── .gitignore                       ← Git ignore rules (includes notes/journey docs)
├── README.md                        ← Project overview & design goals
└── PROGRESS.md                      ← Day-by-day learning milestones log
```

---

## 🧠 Architecture & Mental Model (Week 2 Multi-Layer Boundary)

```
                             ┌──────────────────┐
                             │   User Prompt    │
                             └────────┬─────────┘
                                      │
                                      ▼
                               ┌─────────────┐
                               │  AgentLoop  │ ◄─────────────────────────────────────────┐
                               └──────┬──────┘                                           │
                                      │                                                  │
             ┌────────────────────────┴────────────────────────┐                         │
             ▼                                                 ▼                         │
    ToolCallingClient                                  LLM Structured Output             │
       (Protocol)                                        (Untrusted Boundary)            │
             │                                                 │                         │
     LLM API / Fake                                            ▼                         │
             │                                  ┌─────────────────────────────┐          │
             │                                  │  Layer 1: Intent Validation │          │
             │                                  │  (Decision: tool vs answer) │          │
             │                                  └──────────────┬──────────────┘          │
             │                                                 │                         │
             ▼                                                 ▼                         │
       ToolCall request ──────────────────────────────► ┌─────────────────────────────┐  │
                                                        │ Layer 2: Argument Validation│  │
                                                        │ (ToolArgs via SchemaRegistry│  │
                                                        └──────────────┬──────────────┘  │
                                                                       │                 │
                                               ┌───────────────────────┴───────────────┐ │
                                               │ Invalid                               │ │ Valid
                                               ▼                                       ▼ │
                                    ┌───────────────────────┐                 ┌──────────────────┐
                                    │ format_validation_err │                 │ Layer 3: Security│
                                    │ (compact observation) │                 │ (Workspace path) │
                                    └──────────┬────────────┘                 └────────┬─────────┘
                                               │                                       │
                                               │                              ┌────────┴─────────┐
                                               │                              │ Layer 4: Executor│
                                               │                              │ (Timing & try/ex)│
                                               │                              └────────┬─────────┘
                                               │                                       │
                                               │                                       ▼
                                               │                                 Concrete Tool
                                               │                                 (list/read/search)
                                               │                                       │
                                               │                              ┌────────┴─────────┐
                                               │                              │ ExecutionHistory │
                                               │                              │ (Telemetry JSON) │
                                               │                              └────────┬─────────┘
                                               │                                       │
                                               └────────► Structured Observation ◄─────┘
                                                          (appended to conversation)
```

### Core Concepts in Agentic Software (Week 1 & Week 2)
1. **AgentLoop is Orchestration, NOT Intelligence**: LLM က decision ချတယ်၊ Tool က action လုပ်တယ်၊ `Workspace` က security ထိန်းတယ်၊ `ToolExecutor` က execution time နဲ့ error ကိုဖမ်းတယ်၊ `AgentState` က state သိမ်းတယ်၊ `AgentLoop` က အားလုံးကို coordinate လုပ်ပေးတာသာ ဖြစ်တယ်။
2. **LLM Output as an Untrusted Boundary**: LLM မှ ထွက်လာသော text သို့မဟုတ် JSON သည် အမြဲ unverified input ဖြစ်သည်။ ထို့ကြောင့် machine-verifiable `Decision` contract ဖြင့် wrap လုပ်ပြီး Pydantic validation boundary ဖြတ်ရသည်။
3. **Four-Layer Defense in Depth**:
   - **Layer 1: Agent Intent Validation (`Decision`)**: LLM သည် `tool_call` သို့မဟုတ် `final_answer` တစ်ခုခုကိုသာ ပြုလုပ်ရမည် (နှစ်ခုစလုံးပြိုင်တူမရ၊ အပို fields `extra="forbid"` မရ)။
   - **Layer 2: Tool Argument Validation (`ToolArgs` + `ToolArgumentRegistry`)**: Tool argument တိုင်းကို Pydantic strictly စစ်ဆေးသည် (type checking, string whitespace stripping, non-empty validation, positive bounds)။
   - **Layer 3: Security & Authorization Boundary (`Workspace`)**: Argument မှန်သော်လည်း workspace ပြင်ပသို့ path traversal (`../../secret.txt`) ကျူးလွန်ခြင်းကို တားဆီးသည်။
   - **Layer 4: Execution & Exception Boundary (`ToolExecutor`)**: OS-level သို့မဟုတ် runtime exceptions များကို catch လုပ်ပြီး `ToolExecution(success=False)` အဖြစ် safe wrapping လုပ်သည်။
4. **Structured Validation Error Observation**: Pydantic validation error တက်ပါက python traceback အကြီးကြီး LLM ဆီ မပို့ဘဲ `format_validation_error` ဖြင့် compact machine-readable observation (`field`, `message`, `type`) အဖြစ် ပြောင်းလဲပေးပို့သည်။ LLM သည် မည်သည့် argument မှားယွင်းသွားသည်ကို တိကျစွာသိရှိပြီး self-heal လုပ်နိုင်သည်။
5. **Context Budget Foundation**: `read_file` တွင် `max_bytes` limit ထားခြင်း၊ `search_text` တွင် `max_results` limit ထားခြင်းတို့သည် LLM context window မပြည့်လျှံစေရန် Week 9 context budget အတွက် အခြေခံဖြစ်တယ်။

### 🏛️ Separation of Concerns in Agent Runtime (တာဝန်ခွဲဝေမှုစည်းမျဉ်း)

| Component | Responsibility (တာဝန်) | မလုပ်သင့်သည့်အရာ (Anti-pattern) |
|---|---|---|
| **LLM** | **Decide** — မည်သည့် tool ကို မည်သည့် arguments ဖြင့် ခေါ်မည်ကို ဆုံးဖြတ်ခြင်း၊ Error observation ရရှိပါက Re-plan လုပ်ခြင်း | Execution ကိုယ်တိုင်လုပ်ခြင်း မရှိ |
| **AgentLoop** | **Coordinate** — LLM response ရယူခြင်း၊ tools များသို့ dispatch လုပ်ခြင်း၊ history သိမ်းခြင်း၊ iteration limit စောင့်ကြည့်ခြင်း | Intelligence မပါဝင်၊ Re-planning မလုပ် |
| **Decision & ToolArgs** | **Validate Contract** — Untrusted LLM output ကို machine-verifiable schema အရ type, bounds, fields စစ်ဆေးခြင်း | File system စစ်ဆေးခြင်း သို့မဟုတ် OS logic မပါဝင်ရ |
| **ToolArgumentRegistry** | **Schema Lookup** — Tool name အလိုက် သက်ဆိုင်ရာ Pydantic argument model နှင့် ချိတ်ဆက် validate လုပ်ပေးခြင်း | Execution logic မပါဝင်ရ |
| **ToolExecutor** | **Execute safely** — Tool lookup လုပ်ခြင်း၊ run ခြင်း၊ timing တိုင်းတာခြင်း၊ error catch လုပ်ခြင်း | Re-plan မလုပ်ပါ! Error တက်ပါက `ToolExecution(success=False)` ပြန်ပေးရုံသာ |
| **Workspace** | **Enforce security** — Centralized path resolution နှင့် Path Traversal (`../../`) တားဆီးခြင်း | File parsing / searching logic မပါဝင်ရ |
| **Tool** | **Perform operation** — Concrete OS/File logic (ဖိုင်ဖတ်ခြင်း၊ ရှာဖွေခြင်း) ကို လုပ်ဆောင်ခြင်း | Security စစ်ဆေးမှုများကို tool တိုင်းတွင် duplicate မလုပ်ရ |

### ⚖️ Comparison of Three Structured-Output Strategies

| Strategy | Implementation in Repo | Pros (အားသာချက်) | Cons (အားနည်းချက်) | Best Use Case |
|---|---|---|---|---|
| **1. Prompt-based JSON** | `parse_prompt_json(raw_output)` | Provider အားလုံးတွင် သုံးနိုင်သည်၊ Custom setup မလိုပါ | LLM က JSON syntax error ဖြစ်နိုင်သည်၊ Schema အတိအကျမလိုက်နာနိုင်ပါ | Fallback strategy သို့မဟုတ် basic models များအတွက် |
| **2. Constrained Decoding** | `validate_structured_payload(payload)` | Model generating လုပ်ချိန်မှာပင် Grammar / JSON schema အတိုင်း constrained လုပ်ထားသဖြင့် 100% valid JSON ရရှိသည် | Provider-specific ဖြစ်သည် (e.g. OpenAI JSON Schema mode / Outlines / Guidance) | High-reliability production systems |
| **3. Tool-Call as Schema** | `to_openai_tool()` + native function calling | Established API standard ဖြစ်သည်၊ Provider အများစု natively support လုပ်သည် | Tool calling API overhead ရှိသည်၊ Decision intent နှင့် ရောထွေးနိုင်သည် | Multi-turn agent loops with function execution |

### 🛡️ Schema Validity vs. Semantic Correctness vs. Security Boundary

```
[ Raw LLM Output ]
       │
       ▼  1. Syntax Validity       (Is it valid JSON?)
       │
       ▼  2. Schema Validity       (Does it conform to Decision and ToolArgs types?)
       │
       ▼  3. Semantic Correctness  (Does this file exist? Is query logical?)
       │
       ▼  4. Security Boundary     (Does path escape the Workspace sandbox?)
       │
[ Safe Tool Execution ]
```

> **အရေးကြီးသော ခွဲခြားမှု:**
> - Schema validity (`ReadFileArgs(path="abc.txt", max_bytes=100)`) အောင်မြင်ရုံဖြင့် ဖိုင်ရှိသည် သို့မဟုတ် လုံခြုံသည်ဟု မဆိုနိုင်ပါ။
> - Schema validation ၏ တာဝန်မှာ **data types, bounds, unexpected fields** များကို စစ်ဆေးရန်သာ ဖြစ်သည်။
> - Path traversal (`path="../../secret.txt"`) သည် Schema အရ valid string ဖြစ်သော်လည်း **Workspace security boundary** ကသာ ပိတ်ပင်တားဆီးရမည်ဖြစ်သည်။ တာဝန်များကို ရှင်းလင်းစွာ ခွဲခြားထားသည်။

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

**ဘာလုပ်သလဲ:** `app.agent` package မှ အဓိက classes, models နှင့် functions များကို သန့်ရှင်းစွာ export လုပ်ပေးသော file ဖြစ်သည်။ Week 2 တွင် Decision, Structured Output, Validation Errors export များ တိုးချဲ့ထားသည်။

| Exported Symbol | Type | တာဝန် |
|---|---|---|
| `AgentLoop` | Class | Multi-turn agent orchestrator loop |
| `AgentState` | Dataclass | Loop state machine (status, iteration, conversation, history) |
| `AgentStatus` | Enum | Loop states (`RUNNING`, `COMPLETED`, `MAX_ITERATIONS`, `FAILED`) |
| `Decision` | Pydantic Model | 🆕 Machine-verifiable Agent Decision contract |
| `DecisionAction` | Enum | 🆕 Action types (`tool_call`, `final_answer`) |
| `decision_json_schema` | Function | 🆕 Generates JSON schema for Decision model |
| `ExecutionHistory` | Class | Tool execution audit log & telemetry store |
| `ExecutionRecord` | Dataclass | Single tool execution snapshot record |
| `format_validation_error` | Function | 🆕 Converts Pydantic ValidationError to observation dict |
| `parse_prompt_json` | Function | 🆕 Parses raw LLM JSON text into Decision |
| `run_single_iteration` | Function | Day 3 single iteration helper |
| `StructuredOutputError` | Exception | 🆕 Raised when output parsing or validation fails |
| `validate_structured_payload` | Function | 🆕 Validates provider structured output dictionary |

```python
from .decision import Decision, DecisionAction
from .decision_schema import decision_json_schema
from .history import ExecutionHistory, ExecutionRecord
from .loop import AgentLoop
from .single_iteration import run_single_iteration
from .state import AgentState, AgentStatus
from .structured_output import (
    StructuredOutputError,
    parse_prompt_json,
    validate_structured_payload,
)
from .validation_errors import format_validation_error

__all__ = [
    "AgentLoop",
    "AgentState",
    "AgentStatus",
    "Decision",
    "DecisionAction",
    "ExecutionHistory",
    "ExecutionRecord",
    "StructuredOutputError",
    "decision_json_schema",
    "format_validation_error",
    "parse_prompt_json",
    "run_single_iteration",
    "validate_structured_payload",
]
```

### 3. `app/agent/decision.py` — Machine-Verifiable Decision Schema 🆕

**ဘာလုပ်သလဲ:** LLM ထံမှ ရရှိလာသော ဆုံးဖြတ်ချက် (Decision) ကို Machine-verifiable contract အဖြစ် သတ်မှတ်ပေးသော Pydantic model ဖြစ်သည်။ LLM သည် လုပ်ဆောင်ချက် ၂ မျိုးထဲမှ တစ်ခုတည်းကိုသာ ရွေးချယ်ခွင့်ရှိသည်:
1. `tool_call`: Tool ခေါ်ဆိုခြင်း (`tool_name` နှင့် `arguments` မဖြစ်မနေပါရမည်၊ `final_answer` လုံးဝမပါရ)
2. `final_answer`: အဖြေထုတ်ပေးခြင်း (`final_answer` မဖြစ်မနေပါရမည်၊ `tool_name` နှင့် `arguments` လုံးဝမပါရ)
ထို့အပြင် `model_config = ConfigDict(extra="forbid")` ထားရှိသဖြင့် LLM က hallucinate ဖြစ်ပြီး ထည့်ပေးလိုက်သော မလိုအပ်သည့် extra fields (ဥပမာ `confidence: 0.99`) များကို တင်းကြပ်စွာ ငြင်းပယ်သည်။

| Class / Method | Type | တာဝန် |
|---|---|---|
| `DecisionAction` | Enum (`str, Enum`) | ဆုံးဖြတ်ချက် အမျိုးအစားများ: `TOOL_CALL = "tool_call"`, `FINAL_ANSWER = "final_answer"` |
| `Decision` | Pydantic `BaseModel` | Strict Decision contract (`extra="forbid"`, `action`, `tool_name`, `arguments`, `final_answer`) |
| `Decision.validate_action_payload()` | `@model_validator(mode="after")` | `tool_call` တွင် `tool_name` နှင့် `arguments` ပါရမည်၊ `final_answer` မပါရ။ `final_answer` တွင် `final_answer` ပါရမည်၊ `tool_name`/`arguments` မပါရကြောင်း mutual exclusivity စစ်ဆေးခြင်း |

```python
from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, model_validator


class DecisionAction(str, Enum):
    TOOL_CALL = "tool_call"
    FINAL_ANSWER = "final_answer"


class Decision(BaseModel):
    """
    Machine-verifiable decision produced by the LLM.

    A Decision represents exactly one of two agent actions:

    1. tool_call
    2. final_answer

    The model is intentionally strict because this object becomes
    a trusted boundary between untrusted LLM output and the runtime.
    """

    model_config = ConfigDict(extra="forbid")

    action: DecisionAction

    tool_name: str | None = None
    arguments: dict[str, Any] | None = None
    final_answer: str | None = None

    @model_validator(mode="after")
    def validate_action_payload(self) -> "Decision":
        if self.action == DecisionAction.TOOL_CALL:
            if not self.tool_name:
                raise ValueError(
                    "tool_call decision requires tool_name"
                )

            if self.arguments is None:
                raise ValueError(
                    "tool_call decision requires arguments"
                )

            if self.final_answer is not None:
                raise ValueError(
                    "tool_call decision cannot contain final_answer"
                )

        if self.action == DecisionAction.FINAL_ANSWER:
            if not self.final_answer:
                raise ValueError(
                    "final_answer decision requires final_answer"
                )

            if self.tool_name is not None:
                raise ValueError(
                    "final_answer decision cannot contain tool_name"
                )

            if self.arguments is not None:
                raise ValueError(
                    "final_answer decision cannot contain arguments"
                )

        return self
```

### 4. `app/agent/decision_schema.py` — Decision JSON Schema Generator 🆕

**ဘာလုပ်သလဲ:** `Decision` Pydantic model မှ JSON Schema specification ကို auto-generate လုပ်ပေးသော helper function ဖြစ်သည်။ ဤ schema ကို LLM system prompt ထဲ ထည့်သွင်းရန် သို့မဟုတ် OpenAI structured outputs (`response_format={"type": "json_schema", ...}`) တွင် ပို့ရန် သုံးသည်။

| Function | တာဝန် |
|---|---|
| `decision_json_schema() -> dict[str, Any]` | `Decision.model_json_schema()` ကို ခေါ်ယူပြီး JSON schema dictionary ပြန်ပေးသည်။ |

```python
from typing import Any

from .decision import Decision


def decision_json_schema() -> dict[str, Any]:
    """
    Return the JSON Schema exposed to an LLM provider
    or used by tests/documentation.
    """

    return Decision.model_json_schema()
```

### 5. `app/agent/structured_output.py` — Structured Output Parsing & Validation 🆕

**ဘာလုပ်သလဲ:** LLM မှ ရရှိလာသော output ကို `Decision` object အဖြစ် parse လုပ်ခြင်းနှင့် validation ပြုလုပ်ခြင်းဆိုင်ရာ runtime functions များနှင့် protocol ဖြစ်သည်။ Prompt-based JSON decoding နှင့် Provider-side constrained decoding နှစ်မျိုးစလုံးကို independent validation boundary ဖြင့် ကာကွယ်ပေးထားသည်။

| Component | Type | တာဝန် |
|---|---|---|
| `StructuredOutputError` | Exception | Structured output parsing သို့မဟုတ် validation မအောင်မြင်ပါက ထွက်ပေါ်မည့် custom exception |
| `StructuredDecisionClient` | Protocol | Provider-specific constrained decoding client contract (`generate_decision(prompt, schema) -> dict[str, Any]`) |
| `parse_prompt_json(raw_output)` | Function | Prompt-based JSON ကို `json.loads()` ဖြင့် decode လုပ်ပြီး `Decision.model_validate()` ဖြင့် validate လုပ်သည်။ |
| `validate_structured_payload(payload)` | Function | Provider က generate လုပ်ပေးလိုက်သော dictionary payload ကို Runtime ဘက်မှ independent အနေဖြင့် validate လုပ်သည်။ |

```python
import json
from typing import Any, Protocol

from pydantic import ValidationError

from .decision import Decision


class StructuredOutputError(Exception):
    """Raised when structured LLM output cannot be parsed or validated."""


class StructuredDecisionClient(Protocol):
    """
    Provider-facing abstraction for structured decision generation.

    Implementations may use:
    - constrained decoding
    - provider-native structured outputs
    - another schema-enforcing mechanism
    """

    def generate_decision(
        self,
        prompt: str,
        schema: dict[str, Any],
    ) -> dict[str, Any]:
        ...


def parse_prompt_json(raw_output: str) -> Decision:
    """
    Parse JSON produced by a prompt-based structured-output strategy.
    """

    try:
        payload: dict[str, Any] = json.loads(raw_output)
    except json.JSONDecodeError as exc:
        raise StructuredOutputError(
            f"Invalid JSON: {exc.msg}"
        ) from exc

    try:
        return Decision.model_validate(payload)
    except ValidationError as exc:
        raise StructuredOutputError(
            f"Decision schema validation failed: {exc}"
        ) from exc


def validate_structured_payload(
    payload: dict[str, Any],
) -> Decision:
    """
    Validate a provider-produced structured payload.

    The provider is responsible for constraining generation.
    The runtime still validates the result independently.
    """

    try:
        return Decision.model_validate(payload)
    except ValidationError as exc:
        raise StructuredOutputError(
            f"Decision schema validation failed: {exc}"
        ) from exc
```

### 6. `app/agent/validation_errors.py` — Structured Validation Error Formatter 🆕

**ဘာလုပ်သလဲ:** Pydantic ၏ ရှည်လျားသော traceback သို့မဟုတ် verbose validation error string များကို LLM ဖတ်ရှုနားလည်နိုင်သော compact, machine-readable observation JSON dict အဖြစ် ပြောင်းလဲပေးသည်။ Error ဖြစ်ပွားသည့် field path, human-readable message, error type များကို structured format ဖြင့် ပြန်ပို့ပေးသဖြင့် LLM သည် မည်သည့် argument မှားယွင်းသည်ကို သိရှိပြီး ချက်ချင်း self-correct လုပ်နိုင်သည်။

| Function | Parameter | Output Shape |
|---|---|---|
| `format_validation_error()` | `tool_name: str`, `error: ValidationError` | `{"success": False, "error_type": "tool_argument_validation", "tool_name": tool_name, "message": "...", "errors": [{"field": "...", "message": "...", "type": "..."}]}` |

```python
from typing import Any

from pydantic import ValidationError


def format_validation_error(
    tool_name: str,
    error: ValidationError,
) -> dict[str, Any]:
    """
    Convert Pydantic validation errors into a compact,
    machine-readable observation suitable for an LLM.
    """

    errors: list[dict[str, Any]] = []

    for item in error.errors():
        location = ".".join(
            str(part)
            for part in item.get("loc", ())
        )

        errors.append(
            {
                "field": location,
                "message": item.get("msg", "Invalid value"),
                "type": item.get("type", "validation_error"),
            }
        )

    return {
        "success": False,
        "error_type": "tool_argument_validation",
        "tool_name": tool_name,
        "message": (
            f"Invalid arguments for tool '{tool_name}'."
        ),
        "errors": errors,
    }
```

### 7. `app/agent/state.py` — Agent State Machine 🔄

**ဘာလုပ်သလဲ:** Agent loop တစ်ခုလုံး၏ mutable runtime state ကို ထိန်းသိမ်းသော dataclass ဖြစ်သည်။ Conversation history, current iteration counter, loop status, final response, error message နှင့် runtime telemetry အတွက် `ExecutionHistory` တို့ ပါဝင်သည်။

| Attribute / Property | Type | ရှင်းလင်းချက် |
|---|---|---|
| `conversation` | `list[dict[str, Any]]` | LLM နှင့် အပြန်အလှန်ပြောဆိုထားသော message list |
| `iteration` | `int` | လက်ရှိရောက်ရှိနေသော iteration အကြိမ်အရေအတွက် |
| `status` | `AgentStatus` | Loop ရဲ့ current status (`RUNNING`, `COMPLETED`, `MAX_ITERATIONS`, `FAILED`) |
| `final_response` | `str | None` | Agent ပြီးဆုံးချိန်တွင် user မြင်တွေ့ရမည့် final answer |
| `error` | `str | None` | Agent crash/failure ဖြစ်ခဲ့ပါက သိမ်းဆည်းမည့် error message |
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

### 8. `app/agent/history.py` — Execution Telemetry & Audit Log 🆕

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

### 9. `app/agent/loop.py` — Agent Loop Orchestrator 🔄

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

### 10. `app/agent/single_iteration.py` — Single Iteration Loop (Day 3 Foundation)

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

### 11. `app/llm/__init__.py` — LLM Module Exports

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

### 12. `app/llm/client.py` — Abstract LLM Interface (ADR-0001)

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

### 13. `app/llm/fake_client.py` — Test Fake LLM Client 🔄

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

### 14. `app/llm/openai_client.py` — Real OpenAI/Groq Client 🔄

**ဘာလုပ်သလဲ:** OpenAI SDK (`client.responses.create`) ကို အသုံးပြု၍ Groq endpoint (`api.groq.com/openai/v1`) မှတဆင့် real LLM calls များ ပြုလုပ်ပေးသော implementation ဖြစ်သည်။ Single iteration နှင့် Multi-turn `AgentLoop` နှစ်မျိုးစလုံးအတွက် support လုပ်ထားသည်။

| Method | တာဝန် |
|---|---|
| `__init__()` | `OPENAI_API_KEY`, `OPENAI_MODEL`, `OPENAI_TEMPERATURE` များကို load လုပ်ပြီး Groq base_url ဖြင့် client initialize လုပ်သည်။ |
| `ask()` | Tool မပါသော ရိုးရိုး prompt မေးမြန်းခြင်း |
| `ask_with_tools()` | Prompt နှင့် tools များကို ပို့ပြီး ပထမဆုံး response နှင့် tool calls များကို ပြန်ယူသည်။ |
| `continue_with_tool_outputs()` | Day 3 single iteration အတွက် tool outputs များကို conversation ထဲ ထည့်သွင်း၍ နောက်ဆက်တွဲ final response တောင်းဆိုသည်။ |
| `respond_with_tools()` | Multi-turn `AgentLoop` အတွက် conversation history အပြည့်အစုံနှင့် tools များကို ပို့ပြီး response နှင့် tool calls များကို parse လုပ်ပေးသည်။ |

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

### 15. `app/llm/openai_tools.py` — Tool Format Converter

**ဘာလုပ်သလဲ:** Runtime ၏ provider-independent `Tool` specification ကို OpenAI function calling API လက်ခံနိုင်သော JSON schema format သို့ ပြောင်းလဲပေးသည်။

| Function | တာဝန် |
|---|---|
| `to_openai_tool(tool: Tool) -> dict[str, Any]` | Tool မှ `name`, `description`, `parameters` များကို ထုတ်ယူပြီး `type: "function"` ဖြင့် OpenAI tool format သို့ convert လုပ်ပေးသည်။ |

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

### 16. `app/tools/__init__.py` — Tools Module Exports 🔄

**ဘာလုပ်သလဲ:** `app.tools` package မှ Tool base classes, concrete file tools, schemas, argument registry, `Workspace` security boundary နှင့် execution components များကို export လုပ်ပေးသော file ဖြစ်သည်။

| Exported Symbol | တာဝန် |
|---|---|
| `Tool` | Abstract base class |
| `ToolCall`, `ToolExecution` | Data models |
| `ToolExecutor`, `ToolRegistry` | Execution runtime & lookup store |
| `ToolArgumentRegistry` | 🆕 Pydantic argument schema registry |
| `Workspace` | Security boundary class (Path traversal protection) |
| `ListFilesTool` | Workspace-aware directory listing |
| `ReadFileTool` | Workspace-aware UTF-8 reader with size limit |
| `SearchTextTool` | Workspace-aware text search tool |

```python
from .argument_registry import ToolArgumentRegistry
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
    "ToolArgumentRegistry",
    "ToolCall",
    "ToolExecution",
    "ToolExecutor",
    "ToolRegistry",
    "Workspace",
]
```

### 17. `app/tools/schemas.py` — Pydantic Tool Argument Schemas 🆕

**ဘာလုပ်သလဲ:** Tool arguments များကို untrusted input အဖြစ် သတ်မှတ်ပြီး Pydantic ဖြင့် strict validation စည်းမျဉ်းများ သတ်မှတ်ထားသော schema file ဖြစ်သည်။ Extra fields ပိတ်ပင်ခြင်း (`extra="forbid"`), whitespace strip လုပ်ခြင်း, empty path/query ပိတ်ပင်ခြင်းနှင့် positive bounds (`gt=0`) များကို စစ်ဆေးသည်။

| Model | Inherits | Fields & Validations |
|---|---|---|
| `ToolArgs` | `BaseModel` | Base model with `extra="forbid"`, `str_strip_whitespace=True` |
| `ListFilesArgs` | `ToolArgs` | `path: str = ""` (default workspace root) |
| `ReadFileArgs` | `ToolArgs` | `path: str` (non-empty validator), `max_bytes: int = 100_000` (`gt=0`) |
| `SearchTextArgs` | `ToolArgs` | `query: str` (non-empty validator), `path: str = ""`, `max_results: int = 50` (`gt=0`), `max_file_bytes: int = 100_000` (`gt=0`) |

```python
from pydantic import BaseModel, ConfigDict, Field, field_validator


class ToolArgs(BaseModel):
    """
    Base class for all tool argument models.

    Tool arguments are treated as untrusted input coming from
    the LLM and therefore use strict validation rules.
    """

    model_config = ConfigDict(
        extra="forbid",
        str_strip_whitespace=True,
    )


class ListFilesArgs(ToolArgs):
    """
    Arguments for list_files.
    """

    path: str = ""


class ReadFileArgs(ToolArgs):
    """
    Arguments for read_file.
    """

    path: str
    max_bytes: int = Field(
        default=100_000,
        gt=0,
    )

    @field_validator("path")
    @classmethod
    def validate_path(cls, value: str) -> str:
        if not value:
            raise ValueError("path must not be empty")

        return value


class SearchTextArgs(ToolArgs):
    """
    Arguments for search_text.
    """

    query: str
    path: str = ""
    max_results: int = Field(
        default=50,
        gt=0,
    )
    max_file_bytes: int = Field(
        default=100_000,
        gt=0,
    )

    @field_validator("query")
    @classmethod
    def validate_query(cls, value: str) -> str:
        if not value:
            raise ValueError("query must not be empty")

        return value
```

### 18. `app/tools/argument_registry.py` — Tool Argument Registry 🆕

**ဘာလုပ်သလဲ:** Tool name အလိုက် သက်ဆိုင်ရာ Pydantic argument model နှင့် ချိတ်ဆက်ပေးထားပြီး LLM မှ ရရှိလာသော untrusted arguments dictionary ကို validate လုပ်ပေးသော registry ဖြစ်သည်။

| Method | တာဝန် |
|---|---|
| `__init__()` | `"list_files": ListFilesArgs`, `"read_file": ReadFileArgs`, `"search_text": SearchTextArgs` mapping ကို တည်ဆောက်သည်။ |
| `get_schema(tool_name)` | သက်ဆိုင်ရာ argument model class ကို ပြန်ပေးသည်။ မရှိပါက `ValueError` ပေးသည်။ |
| `validate(tool_name, arguments)` | Tool argument dictionary ကို `schema.model_validate(arguments)` ဖြင့် parse & validate လုပ်ပေးသည်။ |

```python
from typing import Any

from pydantic import BaseModel

from app.tools.schemas import (
    ListFilesArgs,
    ReadFileArgs,
    SearchTextArgs,
)


class ToolArgumentRegistry:
    """
    Maps tool names to their Pydantic argument schemas.
    """

    def __init__(self) -> None:
        self._schemas: dict[str, type[BaseModel]] = {
            "list_files": ListFilesArgs,
            "read_file": ReadFileArgs,
            "search_text": SearchTextArgs,
        }

    def get_schema(self, tool_name: str) -> type[BaseModel]:
        try:
            return self._schemas[tool_name]
        except KeyError as exc:
            raise ValueError(
                f"No argument schema registered for tool: {tool_name}"
            ) from exc

    def validate(
        self,
        tool_name: str,
        arguments: dict[str, Any],
    ) -> BaseModel:
        schema = self.get_schema(tool_name)

        return schema.model_validate(arguments)
```

### 19. `app/tools/base.py` — Abstract Tool Base Class

**ဘာလုပ်သလဲ:** Agent runtime တွင် tool အသစ်တိုင်း လိုက်နာရမည့် interface (contract) ဖြစ်သည်။

| Property / Method | တာဝန် |
|---|---|
| `name` (abstract property) | Tool ၏ နာမည် (ဥပမာ `list_files`) |
| `description` (abstract property) | Tool ၏ လုပ်ဆောင်ချက် ရှင်းလင်းချက် |
| `parameters` (abstract property) | Tool လက်ခံမည့် arguments များ၏ JSON schema |
| `run(arguments)` (abstract method) | Tool ၏ အဓိက operation logic ကို run ခြင်း |

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

### 20. `app/tools/call.py` — ToolCall Data Class

**ဘာလုပ်သလဲ:** LLM ထံမှ tool ခေါ်ဆိုရန် request ရောက်ရှိလာသည့် snapshot ကို သိမ်းဆည်းသော immutable dataclass ဖြစ်သည်။

| Field | Type | ရှင်းလင်းချက် |
|---|---|---|
| `tool_name` | `str` | ခေါ်ဆိုလိုသော tool နာမည် |
| `arguments` | `dict[str, Any]` | Tool သို့ ပေးပို့မည့် arguments များ |
| `call_id` | `str` | API message tracking အတွက် unique ID (default `"call_default"`) |

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

### 21. `app/tools/execution.py` — ToolExecution Data Class

**ဘာလုပ်သလဲ:** Tool execution တစ်ခု ပြီးဆုံးသွားသည့်အခါ ရလဒ်နှင့် timing ကို သိမ်းဆည်းသော immutable snapshot ဖြစ်သည်။

| Field / Property | Type | ရှင်းလင်းချက် |
|---|---|---|
| `tool_name` | `str` | Run ခဲ့သော tool နာမည် |
| `arguments` | `dict[str, Any]` | ပေးပို့ခဲ့သော arguments များ |
| `result` | `Any` | Tool မှ အောင်မြင်စွာ ပြန်ပေးလိုက်သော data |
| `error` | `str | None` | Error တက်ခဲ့ပါက exception message |
| `duration_ms` | `float` | Tool run ရန် ကြာမြင့်ခဲ့သော အချိန် (milliseconds) |
| `success` (property) | `bool` | `error is None` ဖြစ်ပါက `True` ဖြစ်သည်။ |

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

### 22. `app/tools/executor.py` — Tool Executor (Execution & Exception Boundary)

**ဘာလုပ်သလဲ:** Tool registry ထဲမှ tool ကို lookup လုပ်ပြီး execute လုပ်ပေးသည်။ Timing တိုင်းတာခြင်းနှင့် `# noqa: BLE001` ဖြင့် intentional broad exception boundary ထားရှိပြီး runtime crash မဖြစ်စေရန် safe observation အဖြစ် convert လုပ်ပေးသည်။

| Method | တာဝန် |
|---|---|
| `__init__(registry)` | `ToolRegistry` dependency ကို inject လုပ်သည်။ |
| `execute(tool_name, arguments)` | Start time မှတ်သည် → `registry.get()` ရှာသည် → `tool.run()` run သည် → duration တွက်သည် → `ToolExecution` ပြန်ပေးသည်။ Exception တက်ပါက `ToolExecution(success=False, error=str(exc))` ပြန်ပေးသည်။ |

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

### 23. `app/tools/workspace.py` — Workspace Security Boundary 🆕

**ဘာလုပ်သလဲ:** Agent ၏ filesystem operations များကို workspace directory အတွင်း၌သာ ကန့်သတ်ထားပြီး Path Traversal attacks (`../../secret.txt`, symlink escapes) များကို တားဆီးပေးသော centralized security boundary ဖြစ်သည်။

| Method | တာဝန် |
|---|---|
| `__init__(root)` | Workspace root directory ကို absolute path အဖြစ် resolve လုပ်ထားသည်။ |
| `root` (property) | Resolved root path ကို ပြန်ပေးသည်။ |
| `resolve(path)` | Relative path ကို လက်ခံပြီး workspace root ဖြင့် ပေါင်းစပ်ကာ absolute path အဖြစ် resolve လုပ်သည်။ အကယ်၍ resolved path သည် workspace root ပြင်ပသို့ ရောက်ရှိနေပါက `PermissionError` raise လုပ်သည်။ |

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

### 24. `app/tools/list_files.py` — ListFiles Tool 🔄

**ဘာလုပ်သလဲ:** Workspace directory အတွင်းရှိ files နှင့် subdirectories များကို စစ်ဆေးဖော်ပြပေးသော tool ဖြစ်သည်။

| Component | တာဝန် |
|---|---|
| `name`, `description`, `parameters` | `list_files` tool metadata |
| `run(arguments)` | `workspace.resolve(path)` ဖြင့် လုံခြုံစွာ resolve လုပ်ပြီး directory မဟုတ်ပါက `NotADirectoryError` ပေးသည်၊ directory ဖြစ်ပါက sorted file/dir list ကို ပြန်ပေးသည်။ |

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

### 25. `app/tools/read_file.py` — ReadFile Tool 🆕

**ဘာလုပ်သလဲ:** Workspace အတွင်းရှိ ဖိုင်များကို UTF-8 encoding ဖြင့် ဖတ်ရှုပေးသော tool ဖြစ်သည်။ Context budget foundation အဖြစ် `max_bytes` limit ပါဝင်ပြီး ဖိုင်အရွယ်အစားကြီးမားပါက `ValueError` ပေးသည်။

| Component | တာဝန် |
|---|---|
| `run(arguments)` | `workspace.resolve(path)` ဖြင့် resolve လုပ်သည် → ဖိုင်မရှိပါက `FileNotFoundError` → directory ဖြစ်နေပါက `IsADirectoryError` → ဖိုင်ဆိုဒ်သည် `max_bytes` ထက်ကျော်ပါက `ValueError` → UTF-8 text အဖြစ် decode လုပ်ပြီး `{"path": path, "content": text}` ပြန်ပေးသည်။ |

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

### 26. `app/tools/search_text.py` — SearchText Tool 🆕

**ဘာလုပ်သလဲ:** Workspace အတွင်းရှိ ဖိုင်များထဲတွင် case-insensitive keyword search ပြုလုပ်ပေးသော tool ဖြစ်သည်။ Cognitive Complexity <= 15 စည်းမျဉ်းအရ `_search_file()` helper သီးသန့်ခွဲထုတ်ထားသည်။

| Component | တာဝန် |
|---|---|
| `_search_file()` (helper) | Single file တစ်ခုချင်းစီကို binary check လုပ်ပြီး line-by-line keyword ရှာဖွေပေးသည်။ |
| `run(arguments)` | Recursive rglob ဖြင့် files များကို ရှာဖွေပြီး `max_results` အထိ match ဖြစ်သော line number နှင့် content များကို ပြန်ပေးသည်။ |

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

### 27. `app/tools/registry.py` — Tool Registry

**ဘာလုပ်သလဲ:** Agent အသုံးပြုနိုင်သော tools များကို သိမ်းဆည်းပေးပြီး tool name ဖြင့် lookup လုပ်ပေးသော central store ဖြစ်သည်။

| Method | တာဝန် |
|---|---|
| `register(tool)` | Tool ကို registry ထဲ ထည့်သည်။ နာမည်တူပြီးသားဖြစ်ပါက `ValueError` ပေးသည်။ |
| `get(tool_name)` | နာမည်ဖြင့် tool ရှာပေးသည်။ မရှိပါက `KeyError` ပေးသည်။ |
| `list()` | Register လုပ်ထားသော tool instances အားလုံးကို list အနေဖြင့် ပြန်ပေးသည်။ |

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
### 28. `pyproject.toml` — Project Configuration & Build Tooling

**ဘာလုပ်သလဲ:** Python project ၏ build backend (`hatchling`), dependencies (`openai`, `pydantic`, `python-dotenv`), development tools (`pytest`, `mypy`, `ruff`) နှင့် configuration များကို သတ်မှတ်ထားသည်။

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

### 29. `.env.example` — Environment Variable Template

**ဘာလုပ်သလဲ:** Developer အသစ်များ စတင် run နိုင်ရန် API key နှင့် configuration environment variables template ဖြစ်သည်။

```bash
# Copy this file to .env and fill in your real values.
# Never commit .env to version control.

OPENAI_API_KEY=
OPENAI_MODEL=
OPENAI_TEMPERATURE=
```

### 30. `conftest.py` — Pytest Path Configuration

**ဘာလုပ်သလဲ:** Pytest run သည့်အခါ project root path ကို python path ထဲ ထည့်သွင်းပေးပြီး `from app.xxx import ...` import များ အဆင်ပြေစေရန် လုပ်ဆောင်ပေးသည်။

```python
# conftest.py — project-root conftest
# Placing this file here tells pytest to add the agent-runtime/ directory
# to sys.path so that `from app.xxx import ...` works in all test modules.
```

### 31. `README.md` — Project Overview & Vision

**ဘာလုပ်သလဲ:** Agent Runtime ၏ core philosophy, goals, architecture နှင့် setup များကို ရှင်းပြထားသော document ဖြစ်သည်။

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

### 32. `PROGRESS.md` — Learning Milestones Log

**ဘာလုပ်သလဲ:** Day-by-day learning milestones နှင့် code state များကို မှတ်တမ်းတင်ထားသော log ဖြစ်သည်။

```markdown
## Current

Week 2 / Day 2 — Pydantic Validation
Date: 2026-10-03

## Done

### Week 2 Day 1
- Machine-verifiable Decision schema
- DecisionAction enum
- Structured output strategies comparison
- Prompt-based JSON parsing
- Provider-agnostic structured payload validation
- JSON Schema generation

### Week 2 Day 2
- Added ToolArgs base Pydantic model
- Added ListFilesArgs
- Added ReadFileArgs
- Added SearchTextArgs
- Added strict unknown-field rejection
- Added field-level constraints
- Added ToolArgumentRegistry
- Added tool-name → argument-schema mapping
- Added structured validation error formatter
- Distinguished schema validation from workspace authorization
- Added validation tests for invalid types, missing fields, invalid ranges, and unknown fields

## Key Design Decisions

- `Decision` validates agent-level intent
- `ToolArgs` validates tool-level input contracts
- `ToolArgumentRegistry` maps tool names to their argument schemas
- Pydantic validation happens before tool execution
- Validation errors are converted into structured observations
- Workspace remains responsible for path authorization/security
- Schema validation and execution security remain separate boundaries

## Code State

agent-runtime/
├── app/
│   ├── agent/
│   │   ├── decision.py
│   │   ├── decision_schema.py
│   │   ├── structured_output.py
│   │   └── validation_errors.py
│   └── tools/
│       ├── argument_registry.py
│       └── schemas.py
└── tests/
    ├── test_decision.py
    ├── test_structured_output.py
    ├── test_tool_schemas.py
    ├── test_argument_registry.py
    └── test_validation_errors.py

## Today's Goal

Create a typed Pydantic validation layer for tool arguments
and convert validation failures into structured agent observations.

## Next

Week 2 / Day 3 — Malformed Output + Retry
- Error feedback to LLM
- Bounded retry
- Exponential backoff
- Transient vs permanent errors
- Error taxonomy
```

### 33. `docs/adr/0001-llm-provider-abstraction.md` — ADR-0001: Provider-Independent Interface

**ဘာလုပ်သလဲ:** OpenAI SDK သို့မဟုတ် single provider အပေါ် တိုက်ရိုက်မမှီခိုဘဲ Provider-Independent Interface တည်ဆောက်ရန် ချမှတ်ခဲ့သော Architectural Decision Record ဖြစ်သည်။

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

### 34. `.gitignore` — Git Ignore Rules 🔄

**ဘာလုပ်သလဲ:** Git repository ထဲသို့ commit မလုပ်သင့်သော virtual environment, cache, `.env` secrets များကို ဖယ်ထုတ်ပေးသည်။

```gitignore
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

## 🧪 PART 3: COMPLETE TEST SUITE (`tests/`) — ALL 67 TESTS PASSING

### 35. `tests/test_tools.py` — Tool & Registry Unit Tests (7 tests) 🔄

**ဘာလုပ်သလဲ:** `ToolRegistry` ၏ tool registration, duplicate rejection, lookup, empty handling နှင့် `ListFilesTool` ၏ root/subdirectory listing များကို test လုပ်သည်။

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

### 36. `tests/test_llm_client.py` — Fake LLM Client Unit Tests (2 tests)

**ဘာလုပ်သလဲ:** `FakeLLMClient` ၏ deterministic prompt-response interface နှင့် call history tracking ကို test လုပ်သည်။

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

### 37. `tests/test_openai_tools.py` — OpenAI Tool Schema Conversion Test (1 test)

**ဘာလုပ်သလဲ:** `to_openai_tool()` adapter function သည် runtime tool specifications များကို OpenAI function schema သို့ တိကျစွာ convert လုပ်နိုင်ခြင်း ရှိမရှိ test လုပ်သည်။

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

### 38. `tests/test_single_iteration.py` — Single Iteration Loop Tests (2 tests)

**ဘာလုပ်သလဲ:** Day 3 single iteration flow (LLM → Tool → LLM response) နှင့် tool မပါသော plain response များကို test လုပ်သည်။

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

### 39. `tests/test_agent_state.py` — Agent State Machine Tests (4 tests) 🆕

**ဘာလုပ်သလဲ:** `AgentState` ၏ default initialization, `is_finished` status transitions, failure states နှင့် execution history integration များကို test လုပ်သည်။

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

### 40. `tests/test_agent_loop.py` — Multi-Iteration Agent Loop Tests (4 tests) 🔄

**ဘာလုပ်သလဲ:** Multi-turn loop ၏ happy path, max iteration guard, conversation history continuity နှင့် tool result injection များကို test လုပ်သည်။

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

### 41. `tests/test_workspace.py` — Workspace Security Boundary Tests (3 tests) 🆕

**ဘာလုပ်သလဲ:** Path resolution, subpath resolution နှင့် Path Traversal (`../../secret.txt`) attacks များကို `PermissionError` ဖြင့် အောင်မြင်စွာ block နိုင်ခြင်း ရှိမရှိ test လုပ်သည်။

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

### 42. `tests/test_file_tools.py` — File Tools Integration Tests (4 tests) 🆕

**ဘာလုပ်သလဲ:** `ListFilesTool`, `ReadFileTool`, `SearchTextTool` ၃ ခုစလုံးသည် Workspace security boundary နှင့် integration ကောင်းမွန်စွာ အလုပ်လုပ်ခြင်း ရှိမရှိ test လုပ်သည်။

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

### 43. `tests/test_error_recovery.py` — Day 5 Error Recovery & Security Experiments (13 tests) 🆕

**ဘာလုပ်သလဲ:**
- Exp 1: Tool Error Recovery (Missing file failure ဖြစ်သော်လည်း agent မသေဘဲ self-heal လုပ်ခြင်း)
- Exp 2: Path Traversal Security Defense (PermissionError တက်သော်လည်း agent loop အသက်ရှင်ခြင်း)
- Exp 3: Huge Output Context Budget (max_bytes ကျော်လွန်မှု failure အား observation အဖြစ် ရယူခြင်း)
- Exp 4: Realistic Agent Smoke Test (list_files → read_file → final answer flow)
- Exp 5: Max Iterations Infinite Loop Protection (အဆုံးမရှိ tool call နေပါက MAX_ITERATIONS ဖြင့် safe termination)

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

### 44. `tests/test_decision.py` — Decision Contract & Pydantic Validation Tests (9 tests) 🆕

**ဘာလုပ်သလဲ:**
- `tool_call` decision တည်ဆောက်နိုင်ခြင်း
- `final_answer` decision တည်ဆောက်နိုင်ခြင်း
- `tool_call` တွင် `tool_name` မပါပါက ValidationError တက်ခြင်း
- `tool_call` တွင် `arguments` မပါပါက ValidationError တက်ခြင်း
- `final_answer` တွင် `final_answer` မပါပါက ValidationError တက်ခြင်း
- `tool_call` တွင် `final_answer` ပါလာပါက ValidationError တက်ခြင်း (Mutual Exclusivity)
- `final_answer` တွင် `tool_name` ပါလာပါက ValidationError တက်ခြင်း (Mutual Exclusivity)
- Extra unexpected fields (`confidence: 0.99`) ထည့်ပါက `extra="forbid"` ဖြင့် Reject ဖြစ်ခြင်း
- JSON schema အောင်မြင်စွာ generate လုပ်နိုင်ခြင်း

```python
import pytest
from pydantic import ValidationError

from app.agent.decision import Decision, DecisionAction


def test_tool_call_decision_is_valid() -> None:
    decision = Decision(
        action=DecisionAction.TOOL_CALL,
        tool_name="read_file",
        arguments={
            "path": "app/agent/loop.py",
        },
    )

    assert decision.action == DecisionAction.TOOL_CALL
    assert decision.tool_name == "read_file"
    assert decision.arguments == {
        "path": "app/agent/loop.py",
    }


def test_final_answer_decision_is_valid() -> None:
    decision = Decision(
        action=DecisionAction.FINAL_ANSWER,
        final_answer="The file is implemented correctly.",
    )

    assert decision.action == DecisionAction.FINAL_ANSWER
    assert decision.final_answer == (
        "The file is implemented correctly."
    )


def test_tool_call_requires_tool_name() -> None:
    with pytest.raises(ValidationError):
        Decision(
            action=DecisionAction.TOOL_CALL,
            arguments={},
        )


def test_tool_call_requires_arguments() -> None:
    with pytest.raises(ValidationError):
        Decision(
            action=DecisionAction.TOOL_CALL,
            tool_name="read_file",
        )


def test_final_answer_requires_answer() -> None:
    with pytest.raises(ValidationError):
        Decision(
            action=DecisionAction.FINAL_ANSWER,
        )


def test_tool_call_cannot_have_final_answer() -> None:
    with pytest.raises(ValidationError):
        Decision(
            action=DecisionAction.TOOL_CALL,
            tool_name="read_file",
            arguments={},
            final_answer="This should not exist.",
        )


def test_final_answer_cannot_have_tool_name() -> None:
    with pytest.raises(ValidationError):
        Decision(
            action=DecisionAction.FINAL_ANSWER,
            final_answer="Done.",
            tool_name="read_file",
        )


def test_unknown_fields_are_rejected() -> None:
    with pytest.raises(ValidationError):
        Decision(
            action=DecisionAction.FINAL_ANSWER,
            final_answer="Done.",
            confidence=0.99,
        )


def test_json_schema_can_be_generated() -> None:
    schema = Decision.model_json_schema()

    assert schema["type"] == "object"
    assert "action" in schema["properties"]
    assert "tool_name" in schema["properties"]
    assert "arguments" in schema["properties"]
    assert "final_answer" in schema["properties"]
```

### 45. `tests/test_structured_output.py` — Structured Output Parsing & Validation Tests (6 tests) 🆕

**ဘာလုပ်သလဲ:**
- `parse_prompt_json` ဖြင့် tool call parse လုပ်နိုင်ခြင်း
- `parse_prompt_json` ဖြင့် final answer parse လုပ်နိုင်ခြင်း
- Invalid JSON string ဖြစ်ပါက `StructuredOutputError` ("Invalid JSON") တက်ခြင်း
- Invalid schema ဖြစ်ပါက `StructuredOutputError` ("Decision schema validation failed") တက်ခြင်း
- Provider dictionary payload အား `validate_structured_payload` ဖြင့် validate လုပ်နိုင်ခြင်း
- Invalid provider payload အား `StructuredOutputError` ဖြင့် Reject လုပ်ခြင်း

```python
import pytest

from app.agent.decision import DecisionAction
from app.agent.structured_output import (
    StructuredOutputError,
    parse_prompt_json,
    validate_structured_payload,
)


def test_prompt_json_parses_tool_call() -> None:
    raw_output = """
    {
        "action": "tool_call",
        "tool_name": "read_file",
        "arguments": {
            "path": "app/agent/loop.py"
        }
    }
    """

    decision = parse_prompt_json(raw_output)

    assert decision.action == DecisionAction.TOOL_CALL
    assert decision.tool_name == "read_file"


def test_prompt_json_parses_final_answer() -> None:
    raw_output = """
    {
        "action": "final_answer",
        "final_answer": "The repository uses an AgentLoop."
    }
    """

    decision = parse_prompt_json(raw_output)

    assert decision.action == DecisionAction.FINAL_ANSWER
    assert decision.final_answer == (
        "The repository uses an AgentLoop."
    )


def test_prompt_json_rejects_invalid_json() -> None:
    raw_output = """
    {
        "action": "tool_call",
        "tool_name": "read_file"
    """

    with pytest.raises(StructuredOutputError, match="Invalid JSON"):
        parse_prompt_json(raw_output)


def test_prompt_json_rejects_invalid_schema() -> None:
    raw_output = """
    {
        "action": "something_invalid"
    }
    """

    with pytest.raises(
        StructuredOutputError,
        match="Decision schema validation failed",
    ):
        parse_prompt_json(raw_output)


def test_structured_payload_is_validated() -> None:
    payload = {
        "action": "tool_call",
        "tool_name": "search_text",
        "arguments": {
            "query": "AgentLoop",
        },
    }

    decision = validate_structured_payload(payload)

    assert decision.action == DecisionAction.TOOL_CALL
    assert decision.tool_name == "search_text"


def test_structured_payload_rejects_invalid_payload() -> None:
    payload = {
        "action": "tool_call",
    }

    with pytest.raises(
        StructuredOutputError,
        match="Decision schema validation failed",
    ):
        validate_structured_payload(payload)
```

### 46. `tests/test_tools_schemas.py` — Pydantic Tool Argument Schemas Tests (11 tests) 🆕

**ဘာလုပ်သလဲ:**
- `ListFilesArgs`: default path `""` စစ်ဆေးခြင်း
- `ListFilesArgs`: custom path လက်ခံခြင်း
- `ReadFileArgs`: valid arguments လက်ခံခြင်း
- `ReadFileArgs`: empty path ကို field_validator ဖြင့် reject လုပ်ခြင်း
- `ReadFileArgs`: zero max_bytes (`gt=0`) ကို reject လုပ်ခြင်း
- `ReadFileArgs`: negative max_bytes ကို reject လုပ်ခြင်း
- `ReadFileArgs`: unexpected extra fields ကို `extra="forbid"` ဖြင့် reject လုပ်ခြင်း
- `SearchTextArgs`: valid arguments လက်ခံခြင်း
- `SearchTextArgs`: empty query ကို field_validator ဖြင့် reject လုပ်ခြင်း
- `SearchTextArgs`: invalid max_results (`gt=0`) ကို reject လုပ်ခြင်း
- `SearchTextArgs`: invalid file budget ကို reject လုပ်ခြင်း

```python
import pytest
from pydantic import ValidationError

from app.tools.schemas import (
    ListFilesArgs,
    ReadFileArgs,
    SearchTextArgs,
)


def test_list_files_args_defaults_to_workspace_root() -> None:
    args = ListFilesArgs()

    assert args.path == ""


def test_list_files_args_accepts_path() -> None:
    args = ListFilesArgs(
        path="app",
    )

    assert args.path == "app"


def test_read_file_args_accepts_valid_arguments() -> None:
    args = ReadFileArgs(
        path="app/main.py",
        max_bytes=10_000,
    )

    assert args.path == "app/main.py"
    assert args.max_bytes == 10_000


def test_read_file_args_rejects_empty_path() -> None:
    with pytest.raises(ValidationError):
        ReadFileArgs(
            path="",
        )


def test_read_file_args_rejects_zero_max_bytes() -> None:
    with pytest.raises(ValidationError):
        ReadFileArgs(
            path="app/main.py",
            max_bytes=0,
        )


def test_read_file_args_rejects_negative_max_bytes() -> None:
    with pytest.raises(ValidationError):
        ReadFileArgs(
            path="app/main.py",
            max_bytes=-1,
        )


def test_read_file_args_rejects_unknown_fields() -> None:
    with pytest.raises(ValidationError):
        ReadFileArgs(
            path="app/main.py",
            unexpected=True,
        )


def test_search_text_args_accepts_valid_arguments() -> None:
    args = SearchTextArgs(
        query="AgentLoop",
        path="app",
        max_results=20,
        max_file_bytes=50_000,
    )

    assert args.query == "AgentLoop"
    assert args.path == "app"
    assert args.max_results == 20
    assert args.max_file_bytes == 50_000


def test_search_text_args_rejects_empty_query() -> None:
    with pytest.raises(ValidationError):
        SearchTextArgs(
            query="",
        )


def test_search_text_args_rejects_invalid_max_results() -> None:
    with pytest.raises(ValidationError):
        SearchTextArgs(
            query="AgentLoop",
            max_results=0,
        )


def test_search_text_args_rejects_invalid_file_budget() -> None:
    with pytest.raises(ValidationError):
        SearchTextArgs(
            query="AgentLoop",
            max_file_bytes=-1,
        )
```

### 47. `tests/test_validation_errors.py` — Structured Validation Error Observation Tests (1 test) 🆕

**ဘာလုပ်သလဲ:**
- Pydantic `ValidationError` ဖြစ်ပေါ်သည့်အခါ `format_validation_error()` helper က compact observation dictionary (`success: False`, `error_type: "tool_argument_validation"`, `tool_name`, `errors: [{"field": "max_bytes", ...}]`) အဖြစ် ပြောင်းလဲပေးနိုင်ခြင်း ရှိမရှိ စစ်ဆေးသည်။

```python
from pydantic import ValidationError

from app.agent.validation_errors import (
    format_validation_error,
)
from app.tools.schemas import ReadFileArgs


def test_validation_error_becomes_structured_observation() -> None:
    try:
        ReadFileArgs(
            path="app/main.py",
            max_bytes=-1,
        )
    except ValidationError as error:
        observation = format_validation_error(
            "read_file",
            error,
        )

    assert observation["success"] is False
    assert observation["error_type"] == (
        "tool_argument_validation"
    )
    assert observation["tool_name"] == "read_file"

    errors = observation["errors"]

    assert len(errors) == 1
    assert errors[0]["field"] == "max_bytes"
```

---

## 🔬 ERROR RECOVERY TAXONOMY & CONTEXT ENGINEERING

### Recovery Failure Types (မတူညီသော Error အမျိုးအစား ၃ မျိုး)
1. **Tool Name Hallucination (Experiment 1A):**
   - ဥပမာ: `repo_browser.list_files`
   - Failure: `ToolRegistry.get()` မှ `KeyError` တက်သည်။
   - Recovery: Tool name ကို registry ထဲရှိ valid tool နာမည်အဖြစ် ပြောင်းလဲခေါ်ဆိုသည်။
2. **Schema / Argument Validation Error (Week 2):**
   - ဥပမာ: `read_file(path="", max_bytes=-1)`
   - Failure: Pydantic `ValidationError` ဖြစ်ပြီး `format_validation_error()` မှ structured observation ထုတ်ပေးသည်။
   - Recovery: Argument boundary အမှားကို သိရှိပြီး မှန်ကန်သော type/bounds ဖြင့် ပြန်လည်ပြင်ဆင်ခေါ်ဆိုသည်။
3. **Semantic / Environmental Error (Experiment 1B):**
   - ဥပမာ: `read_file("missing.py")`
   - Failure: `ReadFileTool.run()` မှ `FileNotFoundError` တက်သည်။
   - Recovery: Path အမှားကို နားလည်ပြီး `list_files(".")` ဖြင့် directory ကို အရင်စူးစမ်းကာ မှန်ကန်သော ဖိုင်လမ်းကြောင်းကို ရှာဖွေသည်။

### Context Engineering Preview
> **အဓိက သဘောတရား:** `read_file` failure သို့မဟုတ် validation error ဖြစ်ချိန်တွင် `AgentLoop` က "File မတွေ့ဘူး → `list_files` သုံးလိုက်" ဟု ဘယ်တော့မှ မဆုံးဖြတ်ပါ။ `AgentLoop` သည် `error → observation → conversation` သို့ သယ်ဆောင်ပေးရုံသာ လုပ်သည်။ ထို observation ကို ဖတ်ရှုပြီး **Re-plan လုပ်ကာ self-correct လုပ်သူမှာ LLM သာ ဖြစ်သည်**။
> ထို့ကြောင့် *"Conversation ထဲတွင် မည်သည့် context နှင့် observation format မျိုး ထည့်သွင်းပေးထားလျှင် LLM က အမှားကို အကောင်းဆုံး recover လုပ်နိုင်မည်နည်း?"* ဆိုသည့် မေးခွန်းသည် **Context Engineering** ၏ အခြေခံအုတ်မြစ် ဖြစ်သည်။

---

## 🛑 RUNTIME SAFETY & LIFECYCLE REASONING

### Key Conceptual Distinctions
- **Tool Failure ≠ Agent Failure**: Tool တစ်ခု error တက်ခြင်းသည် Agent run ပျက်စီးခြင်း မဟုတ်ပါ။ အမှန်စင်စစ် LLM အတွက် observation အသစ်ရရှိခြင်း ဖြစ်သည်။
- **Validation Error ≠ Tool Execution Error**: Validation error သည် Tool စတင်မ run မီ runtime boundary ၌ စစ်ဆေးတားဆီးခြင်းဖြစ်ပြီး၊ Tool execution error သည် tool run နေစဉ် OS/Filesystem မှ တက်လာသော error ဖြစ်သည်။
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
| **Protocol (Duck Typing)** | `ToolCallingClient`, `StructuredDecisionClient` | Provider independence (ADR-0001) အရ runtime အား external SDKs များနှင့် တိုက်ရိုက်မချိတ်ဆက်စေခြင်း |
| **Pydantic Strict Boundary** | `Decision`, `ToolArgs` (`extra="forbid"`) | Untrusted LLM output ကို strict schema ဖြင့် စစ်ဆေးပြီး unexpected fields နှင့် invalid types များကို reject လုပ်ခြင်း |
| **Two-Level Validation Pipeline** | `Decision` (Intent) + `ToolArgs` (Arguments) | Agent-level ဆုံးဖြတ်ချက်နှင့် Tool-level inputs များကို တာဝန်ခွဲခြားစစ်ဆေးခြင်း |
| **Dependency Injection** | `ToolExecutor(registry)`, `AgentLoop(client, registry, executor)` | Unit testing တွင် fake dependencies များဖြင့် swap လုပ်ရ လွယ်ကူစေခြင်း |
| **Frozen Dataclass** | `ToolCall`, `ToolExecution`, `ExecutionRecord` | Runtime အချက်အလက်များ မတော်တဆ ပြင်ဆင်မခံရစေရန် Immutability အာမခံခြင်း |
| **Security Boundary Pattern** | `Workspace` | Path traversal attacks များကို tool တိုင်းတွင် duplicate မစစ်ဘဲ single boundary ဖြင့် ဗဟိုချုပ်ကိုင်ခြင်း |
| **Error as Observation** | `ToolExecutor` + `AgentLoop` | Exception ကြောင့် agent မသေစေဘဲ failure အား observation အဖြစ် LLM ထံ ပြန်ပို့၍ self-heal စေခြင်း |
| **Structured Error Observation** | `format_validation_error()` | Traceback အစား compact JSON observation ပို့ပေးသဖြင့် LLM က context token မကုန်ဘဲ self-correct လွယ်ကူခြင်း |
| **Runtime Telemetry** | `ExecutionHistory` + `ExecutionRecord` | Tool execution ကြာချိန် (ms)၊ arguments နှင့် results များကို JSON serialize လုပ်၍ audit log ထားရှိနိုင်ခြင်း |
| **Deterministic Simulation** | `FakeLLMClient.response_sequence` | Network latency သို့မဟုတ် API cost မရှိဘဲ multi-step agent flow များကို deterministically test နိုင်ခြင်း |

---

## 📈 COMPLETE TEST SUITE VERIFICATION (67/67 PASSING)

```
============================= test session starts =============================
platform win32 -- Python 3.12.10, pytest-9.1.1, pluggy-1.6.0
rootdir: C:\Users\uaung\aung_sann_phyo\person\agentic-ai-learning\agent-runtime
configfile: pyproject.toml
testpaths: tests
plugins: anyio-4.15.1
collected 67 items

tests/test_agent_loop.py ....                                            [  5%]
tests/test_agent_state.py ....                                           [ 11%]
tests/test_decision.py .........                                         [ 25%]
tests/test_error_recovery.py .............                               [ 44%]
tests/test_file_tools.py ....                                            [ 50%]
tests/test_llm_client.py ..                                              [ 53%]
tests/test_openai_tools.py .                                             [ 55%]
tests/test_single_iteration.py ..                                        [ 58%]
tests/test_structured_output.py ......                                   [ 67%]
tests/test_tools.py .......                                              [ 77%]
tests/test_tools_schemas.py ...........                                  [ 94%]
tests/test_validation_errors.py .                                        [ 95%]
tests/test_workspace.py ...                                              [100%]

============================== 67 passed in 1.55s ==============================
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

*Updated by Antigravity AI — Agent Runtime Complete Codebase Dump (44 Files, 67 Tests, 100% Passing)*
