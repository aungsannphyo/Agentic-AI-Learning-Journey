# Agent Runtime Codebase Architecture & In-Depth Technical Documentation

ဤ Documentation သည် **Agent Runtime** codebase တစ်ခုလုံးရှိ folder နှင့် file တစ်ခုချင်းစီ၏ Source Code အပြည့်အစုံ၊ Function/Class တစ်ခုချင်းစီ၏ အသေးစိတ်အလုပ်လုပ်ပုံ၊ Design Decisions များနှင့် လက်တွေ့ အသုံးပြုပုံ (Usage) တို့ကို စနစ်တကျ ရှင်းပြထားသော Technical Reference ဖြစ်ပါသည်။

---

## မာတိကာ (Table of Contents)

1. [High-Level Architecture & Lifecycle](#1-high-level-architecture--lifecycle)
2. [Runtime Guard Order & Safety Pipeline](#2-runtime-guard-order--safety-pipeline)
3. [Root & Entry Point Layer](#3-root--entry-point-layer)
   - [`app/main.py`](#appmainpy)
   - [`conftest.py`](#conftestpy)
4. [LLM Subsystem Layer (`app/llm/`)](#4-llm-subsystem-layer-appllm)
   - [`app/llm/client.py`](#appllmclientpy)
   - [`app/llm/openai_client.py`](#appllmopenai_clientpy)
   - [`app/llm/fake_client.py`](#appllmfake_clientpy)
   - [`app/llm/openai_tools.py`](#appllmopenai_toolspy)
   - [`app/llm/__init__.py`](#appllm__init__py)
5. [Tools & Sandbox Execution Layer (`app/tools/`)](#5-tools--sandbox-execution-layer-apptools)
   - [`app/tools/base.py`](#apptoolsbasepy)
   - [`app/tools/call.py`](#apptoolscallpy)
   - [`app/tools/call_parsing.py`](#apptoolscall_parsingpy)
   - [`app/tools/execution.py`](#apptoolsexecutionpy)
   - [`app/tools/workspace.py`](#apptoolsworkspacepy)
   - [`app/tools/schemas.py`](#apptoolsschemaspy)
   - [`app/tools/schema_utils.py`](#apptoolsschema_utilspy)
   - [`app/tools/validation.py`](#apptoolsvalidationpy)
   - [`app/tools/registry.py`](#apptoolsregistrypy)
   - [`app/tools/executor.py`](#apptoolsexecutorpy)
   - [`app/tools/list_files.py`](#apptoolslist_filespy)
   - [`app/tools/read_file.py`](#apptoolsread_filepy)
   - [`app/tools/search_text.py`](#apptoolssearch_textpy)
   - [`app/tools/__init__.py`](#apptools__init__py)
6. [Agent Runtime & Control Layer (`app/agent/`)](#6-agent-runtime--control-layer-appagent)
   - [`app/agent/clock.py`](#appagentclockpy)
   - [`app/agent/budget.py`](#appagentbudgetpy)
   - [`app/agent/usage.py`](#appagentusagepy)
   - [`app/agent/cost.py`](#appagentcostpy)
   - [`app/agent/decision.py`](#appagentdecisionpy)
   - [`app/agent/decision_schema.py`](#appagentdecision_schemapy)
   - [`app/agent/structured_output.py`](#appagentstructured_outputpy)
   - [`app/agent/validation_errors.py`](#appagentvalidation_errorspy)
   - [`app/agent/decision_recovery.py`](#appagentdecision_recoverypy)
   - [`app/agent/history.py`](#appagenthistorypy)
   - [`app/agent/llm_errors.py`](#appagentllm_errorspy)
   - [`app/agent/retry.py`](#appagentretrypy)
   - [`app/agent/resilient_client.py`](#appagentresilient_clientpy)
   - [`app/agent/loop_guard.py`](#appagentloop_guardpy)
   - [`app/agent/state.py`](#appagentstatepy)
   - [`app/agent/loop.py`](#appagentlooppy)
   - [`app/agent/__init__.py`](#appagent__init__py)
7. [Core Design Principles & Takeaways](#7-core-design-principles--takeaways)

---

## 1. High-Level Architecture & Lifecycle

Agent Runtime သည် **LangChain, LangGraph, CrewAI, LlamaIndex** ကဲ့သို့သော ပြင်ပ framework များကို လုံးဝမသုံးဘဲ Python 3.12 native standard libraries နှင့် Official OpenAI SDK ကိုသာ အသုံးပြုကာ သန့်ရှင်းကျစ်လျစ်စွာ တည်ဆောက်ထားသော autonomous software engineering agent ဖြစ်ပါသည်။

### System Flowchart

```mermaid
flowchart TD
    User([User Prompt]) --> Main[app/main.py]
    Main --> AgentLoop[AgentLoop (app/agent/loop.py)]
    
    subgraph Per-Run Guards Factory
        Clock[Clock / RuntimeBudget] --> PerRunBudget[Per-Run BudgetTracker]
        LoopFactory[loop_guard_factory] --> PerRunGuard[Per-Run LoopGuard]
        TokenGuard[TokenBudget / UsageTracker]
    end

    AgentLoop --> PerRunBudget
    AgentLoop --> PerRunGuard
    AgentLoop --> TokenGuard
    AgentLoop --> ResilientClient[ResilientClient (Retry & Error Classifier)]
    ResilientClient --> OpenAIClient[OpenAIClient (Groq/OpenAI Provider)]
    OpenAIClient --> CallParsing[app/tools/call_parsing.py]
    CallParsing --> ToolCallObj[ToolCall (arguments / parse_error)]
    
    subgraph Tool Subsystem (Single Source of Truth)
        ToolArgsModel[Tool.args_model (Pydantic Args)]
        StrictSchema[strict_json_schema()]
        ToolArgsModel --> StrictSchema
        StrictSchema --> ToolInputSchema[Tool.input_schema]
        ToolRegistry[ToolRegistry]
        ToolExecutor[ToolExecutor (Mandatory Validation)]
        Workspace[Workspace Boundary Guard]
        ListFiles[ListFilesTool]
        ReadFile[ReadFileTool]
        SearchText[SearchTextTool]
    end

    ToolArgsModel --> ToolExecutor
    ToolInputSchema --> OpenAIClient
    AgentLoop --> ToolExecutor
    ToolExecutor --> ToolRegistry
    ToolRegistry --> ListFiles & ReadFile & SearchText
    ListFiles & ReadFile & SearchText --> Workspace
    
    ToolExecutor --> History[ExecutionHistory]
    AgentLoop --> AgentState[AgentState (Conversation, Status, Usage)]
```

---

## 2. Runtime Guard Order & Safety Pipeline

`AgentLoop.run()` ထဲတွင် iteration တိုင်းသည် အောက်ပါ guard order အတိုင်း အဆင့်ဆင့် တိကျစွာ လည်ပတ်ပါသည်:

1. **Wall-clock Budget Check**: စုစုပေါင်း ကြာချိန်သတ်မှတ်ချက် ကျော်မကျော် စစ်ဆေးခြင်း (`TIMEOUT`).
2. **Iteration Budget Check**: အမြင့်ဆုံး iteration သတ်မှတ်ချက် ကျော်မကျော် စစ်ဆေးခြင်း (`MAX_ITERATIONS`).
3. **LLM Call Execution**: `ResilientClient` မှတစ်ဆင့် LLM ထံ prompt နှင့် tools များကို ပို့ခြင်း။
   - Error ဖြစ်ပါက retry ပြုလုပ်ခြင်း (Transient ဖြစ်လျှင် exponential backoff ဖြင့် retry; Deadline ကျော်လျှင် `TIMEOUT`; ပျက်စီးလျှင် `LLM_FAILED`).
4. **Usage Recording**: LLM response မှ token usage ကို ဖတ်ပြီး `UsageTracker` တွင် မှတ်တမ်းတင်ခြင်း။
5. **Final Answer Verification**: Model က Tool မခေါ်ဘဲ အဖြေတိုက်ရိုက်ပေးလျှင် `COMPLETED` အဖြစ် ချက်ချင်းလက်ခံခြင်း (Token budget ကျော်လွန်နေသော်လည်း ပြီးစီးသွားသောအဖြေကို လက်ခံသည်)။
6. **Token Budget Check**: Tool side-effects များကို မလုပ်ဆောင်မီ Token budget ကျော်မကျော် စစ်ဆေးခြင်း (`TOKEN_BUDGET_EXCEEDED`).
7. **Per-Tool-Call Safety & Execution**:
   - **Malformed Argument / Parse Error Check**: Model ထံမှ arguments များသည် JSONDecodeError ဖြစ်နေပါက သို့မဟုတ် dict မဟုတ်ပါက runtime crash မဖြစ်စေဘဲ parse error ကို observation အဖြစ် model ထံ ပြန်ပို့ပေးပြီး Loop Guard စစ်ဆေးမှု မတိုင်မီ continue လုပ်ခြင်း။
   - **Loop Guard Check**: Tool arguments fingerprint ကိုစစ်ပြီး တူညီသော Tool Call ထပ်ခါထပ်ခါ ခေါ်နေခြင်းကို ကာကွယ်ခြင်း (`LOOP_DETECTED`).
   - **Mandatory Tool Validation & Execution**: `ToolExecutor` ဖြင့် `tool.args_model` မှတစ်ဆင့် validation စစ်ဆေးပြီး workspace boundary အတွင်း tool ကို execute လုပ်ခြင်း။ ရလဒ် သို့မဟုတ် observation ကို conversation history ထဲသို့ ထည့်သွင်းခြင်း။

---

## 3. Root & Entry Point Layer

### `app/main.py`
အက်ပလီကေးရှင်း စတင် run သော Bootstrapping file ဖြစ်ပါသည်။ Component အားလုံးကို instantiate လုပ်ပြီး Dependency Injection ဖြင့် ချိတ်ဆက် run ပေးပါသည်။

#### Source Code:
```python
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
from app.agent.resilient_client import ResilientClient
from app.agent.retry import RetryPolicy
from app.llm import OpenAIClient
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
        max_iterations=10,
        max_wall_time_seconds=120.0,
        per_call_timeout_seconds=30.0,
    )

    inner = OpenAIClient(
        system_prompt=(
            "You are a software engineering agent. "
            "Use the available tools to inspect the workspace. "
            "Only use workspace-relative paths. "
            "Do not invent file contents."
        ),
        timeout_seconds=runtime_budget.per_call_timeout_seconds,
    )

    client = ResilientClient(inner, RetryPolicy(max_attempts=3))

    agent = AgentLoop(
        client=client,
        registry=registry,
        executor=executor,
        max_iterations=runtime_budget.max_iterations,
        runtime_budget=runtime_budget,
        loop_guard_factory=lambda: LoopGuard(max_repeated_calls=3),
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

    if client.attempt_log:
        print("\n=== LLM Retry Log ===\n")
        for rec in client.attempt_log:
            print(rec)

    print("\n=== Usage Report ===\n")
    print(json.dumps(state.usage.report(), indent=2))

    print("\n=== Execution History ===\n")
    print(state.history.to_json())


if __name__ == "__main__":
    main()
```

#### အသေးစိတ် ရှင်းလင်းချက်:
- `build_registry(workspace)`: ပေးလိုက်သော `Workspace` အပေါ်အခြေခံ၍ `ListFilesTool`, `ReadFileTool`, `SearchTextTool` ၃ ခုကို ဖန်တီးကာ `ToolRegistry` ထဲသို့ မှတ်ပုံတင်ပေးသည်။
- `pricing_from_env()`: Environment variable များဖြစ်သော `MODEL_INPUT_USD_PER_MTOK` နှင့် `MODEL_OUTPUT_USD_PER_MTOK` တို့မှတစ်ဆင့် token ၁ သန်းလျှင် ကုန်ကျမည့် ဒေါ်လာနှုန်းထားကိုဖတ်ပြီး `ModelPricing` object ပြန်ပေးသည်။ သတ်မှတ်မထားပါက `None` ပြန်ပေးသည်။
- `main()`:
  1. `load_dotenv()` ဖြင့် `.env` ဖိုင်မှ environment variables များကို load လုပ်သည်။
  2. လက်ရှိ directory (`Path.cwd()`) ဖြင့် `Workspace` sandbox boundary ကို သတ်မှတ်သည်။
  3. `ToolRegistry` ကို `ToolExecutor(registry)` ထဲသို့ ထည့်သွင်းသည် (`ToolArgumentRegistry` ကို ဖျက်လိုက်ပြီးဖြစ်၍ validation သည် tool တစ်ခုချင်းစီ၏ `args_model` မှတစ်ဆင့် mandatory အလိုအလျောက် စစ်ဆေးသည်)။
  4. `RuntimeBudget` ဖြင့် iteration ၁၀ ကြိမ်၊ wall-clock စက္ကန့် ၁၂၀၊ call တစ်ခုလျှင် ၃၀ စက္ကန့် သတ်မှတ်သည်။
  5. `OpenAIClient` ကို socket timeout ဖြင့် initialize လုပ်ပြီး `ResilientClient` ဖြင့် wrap လုပ်ကာ retry policy (၃ ကြိမ်အထိ) သတ်မှတ်သည်။
  6. `AgentLoop` ကို `runtime_budget` နှင့် `loop_guard_factory=lambda: LoopGuard(max_repeated_calls=3)` ပေးပို့ကာ initialize လုပ်သည်။ `AgentLoop.run()` ခေါ်ချိန်တိုင်းတွင်မှ per-run fresh tracker နှင့် guard များကို runtime အတွင်း ဆောက်လုပ်သည်။
  7. ရရှိလာသော `AgentState` မှ Final Response, Status, LLM Retry Log, Token Usage Report နှင့် Tool Execution History များကို Terminal တွင် print ထုတ်ပေးသည်။

---

### `conftest.py`
Pytest root configuration ဖိုင်ဖြစ်ပါသည်။

#### Source Code:
```python
# conftest.py — project-root conftest
# Placing this file here tells pytest to add the agent-runtime/ directory
# to sys.path so that `from app.xxx import ...` works in all test modules.
```

#### အသေးစိတ် ရှင်းလင်းချက်:
- ပရောဂျက် root တွင် ဤဖိုင်ကို ထားရှိခြင်းဖြင့် `pytest` run သည့်အခါ root folder ကို Python ၏ `sys.path` ထဲသို့ အလိုအလျောက် ထည့်သွင်းပေးပါသည်။ ထို့ကြောင့် `tests/` ဖိုင်များမှ `from app.xxx import ...` ဟု သန့်ရှင်းစွာ import ခေါ်ယူအသုံးပြုနိုင်စေပါသည်။

---

## 4. LLM Subsystem Layer (`app/llm/`)

LLM provider များနှင့် ချိတ်ဆက်လုပ်ဆောင်သော layer ဖြစ်သည်။ မည်သည့် provider ပြောင်းပြောင်း runtime core logic များ မထိခိုက်စေရန် interface ခံထားသည်။

### `app/llm/client.py`
Provider-independent abstract base class ဖြစ်ပါသည်။

#### Source Code:
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

#### အသေးစိတ် ရှင်းလင်းချက်:
- `LLMClient(ABC)`: Python ၏ `abc.ABC` ကို အသုံးပြု၍ Provider interface တစ်ခု သတ်မှတ်ထားသည်။
- `ask(*, system_prompt, user_prompt)`: Tool မပါသော ရိုးရှင်းသည့် prompt-response ဆက်သွယ်မှုအတွက် abstract method ဖြစ်သည်။

---

### `app/llm/openai_client.py`
OpenAI SDK ၏ `responses.create` API (New Responses API) ကို အသုံးပြုထားသော implementation ဖြစ်ပြီး Groq/OpenAI compatible models များနှင့် ချိတ်ဆက်ပါသည်။

#### Source Code:
```python
import os
from typing import Any

from openai import OpenAI

from app.tools import Tool, ToolCall, parse_tool_call

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
        timeout_seconds: float | None = None,
    ) -> None:
        self._client = OpenAI(
            api_key=os.environ["OPENAI_API_KEY"],
            base_url="https://api.groq.com/openai/v1",
            timeout=timeout_seconds,
            max_retries=0,
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
                parse_tool_call(
                    call_id=item.call_id,
                    name=item.name,
                    raw_arguments=item.arguments,
                )
            )

        return response, tool_calls
```

#### အသေးစိတ် ရှင်းလင်းချက်:
- `OpenAI(..., timeout=timeout_seconds, max_retries=0)`:
  - **Design Decision**: `max_retries=0` သတ်မှတ်ထားခြင်းမှာ OpenAI SDK ၏ built-in retry ကို ပိတ်ပြီး၊ ကျွန်ုပ်တို့ ကိုယ်တိုင်ရေးသားထားသော `ResilientClient` Retry Layer ကသာ retry logic ကို အပြည့်အဝ ထိန်းချုပ်စေရန် ဖြစ်သည်။ Socket level timeout ကို `timeout_seconds` ဖြင့် ကာကွယ်ထားသည်။
- `ask()`: Prompt ပို့ပြီး output စာသား (`response.output_text`) ကို တိုက်ရိုက် ပြန်ပေးသည်။
- `respond_with_tools(conversation, tools)`:
  - `AgentLoop` က iteration တိုင်းတွင် အဓိက ခေါ်ယူသည့် single unified function ဖြစ်သည်။
  - Conversation history အပြည့်အစုံနှင့် `to_openai_tool` ဖြင့် convert လုပ်ထားသော tools စာရင်းကို model ထံ ပို့သည်။
  - Response output blocks များထဲမှ `item.type == "function_call"` များကို ရွေးထုတ်ပြီး `parse_tool_call` helper ဖြင့် parse လုပ်ကာ internal `ToolCall` dataclass အဖြစ် ပြောင်းလဲပေးသည်။ Argument string များ malformed ဖြစ်နေပါကလည်း exception မတက်ဘဲ `ToolCall.parse_error` အဖြစ် observation လမ်းကြောင်းသို့ လွှဲပြောင်းပေးသည်။

---

### `app/llm/fake_client.py`
Unit test များတွင် network API မလိုဘဲ deterministic ဖြစ်သော response များ ထုတ်ပေးနိုင်ရန် mock client ဖြစ်ပါသည်။

#### Source Code:
```python
from dataclasses import dataclass, field
from typing import Any

from app.tools import ToolCall, parse_tool_call

from .client import LLMClient


@dataclass
class FakeResponse:
    output_text: str
    output: list[Any] = field(default_factory=list)
    id: str = "fake-response-123"
    usage: Any = None


class FakeLLMClient(LLMClient):
    """Deterministic LLM implementation for tests."""

    def __init__(
        self,
        response: str,
        *,
        response_sequence: list[FakeResponse] | None = None,
    ) -> None:
        self.response = response
        self._response_sequence: list[FakeResponse] = (
            list(response_sequence) if response_sequence else []
        )
        self.calls: list[dict[str, Any]] = []

    def _extract_tool_calls(self, response: FakeResponse) -> list[ToolCall]:
        return [
            parse_tool_call(
                call_id=item.call_id,
                name=item.name,
                raw_arguments=item.arguments,
            )
            for item in response.output
            if item.type == "function_call"
        ]

    def ask(self, *, system_prompt: str, user_prompt: str) -> str:
        self.calls.append(
            {"system_prompt": system_prompt, "user_prompt": user_prompt}
        )
        return self.response

    def respond_with_tools(
        self,
        *,
        conversation: list[dict[str, Any]],
        tools: list[Any],
    ) -> tuple[FakeResponse, list[ToolCall]]:
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

#### အသေးစိတ် ရှင်းလင်းချက်:
- `FakeResponse`: OpenAI SDK ၏ response object ကို simulate လုပ်ထားသည့် dataclass ဖြစ်သည်။ `output_text`, `output` (function calls), `id`, `usage` ပါရှိသည်။
- `FakeLLMClient`:
  - `response_sequence`: Multi-step testing အတွက် response sequence ပေးထားနိုင်သည်။ Iteration တိုင်းတွင် `pop(0)` ဖြင့် sequence ထဲမှ response ကို အစဉ်လိုက် ထုတ်ပေးသည်။ Sequence ကုန်သွားပါက tool call မပါသော default response ကို ပြန်ပေးသဖြင့် Agent loop အလိုအလျောက် ရပ်တန့်စေသည်။
  - `calls`: LLM ထံ ပေးပို့လိုက်သော prompts နှင့် conversations များကို စစ်ဆေး (assert) နိုင်ရန် list ထဲတွင် သိမ်းဆည်းပေးထားသည်။

---

### `app/llm/openai_tools.py`
Internal `Tool` definition ကို OpenAI function tool format သို့ ပြောင်းပေးသည့် converter ဖြစ်သည်။

#### Source Code:
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

#### အသေးစိတ် ရှင်းလင်းချက်:
- `to_openai_tool(tool: Tool)`:
  - Runtime ရှိ `Tool` object မှ `name`, `description`, `input_schema` များကို ယူပြီး OpenAI Responses API မျှော်လင့်ထားသည့် JSON format အဖြစ် ဖွဲ့စည်းပေးသည်။
  - `"strict": True` သတ်မှတ်ထားခြင်းကြောင့် model သည် schema အတိုင်း တိကျစွာ function arguments များကို ထုတ်ပေးရန် enforce လုပ်စေသည်။

---

### `app/llm/__init__.py`
LLM sub-package ၏ Public API exports ဖြစ်သည်။

#### Source Code:
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

---

## 5. Tools & Sandbox Execution Layer (`app/tools/`)

Tools layer သည် Agent ၏ လက်တွေ့လုပ်ဆောင်နိုင်စွမ်း (actions) ဖြစ်ပြီး Filesystem ကို စစ်ဆေးဖတ်ရှုနိုင်သော tools များ၊ sandbox boundary နှင့် arguments validation များ ပါဝင်ပါသည်။

### `app/tools/base.py`
Tool အားလုံး လိုက်နာရမည့် Abstract Base Class ဖြစ်သည်။ Single source of truth pattern အရ tool တစ်ခုချင်းစီသည် argument model (`args_model`) ကိုသာ တစ်နေရာတည်းတွင် ကြေညာပြီး၊ model-facing `input_schema` နှင့် runtime validation နှစ်ခုစလုံးကို ထို model မှ အလိုအလျောက် derive ပြုလုပ်သည်။

#### Source Code:
```python
from abc import ABC, abstractmethod
from typing import Any

from pydantic import BaseModel

from .schema_utils import strict_json_schema


class Tool(ABC):
    """Base abstraction for all agent tools.

    A tool declares its argument model ONCE (args_model). Both the
    model-facing JSON schema and runtime validation derive from it.
    """

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
    def args_model(self) -> type[BaseModel]:
        """Pydantic model describing and validating the tool's input."""
        raise NotImplementedError

    @property
    def input_schema(self) -> dict[str, Any]:
        """Model-facing JSON Schema, derived from args_model."""
        return strict_json_schema(self.args_model)

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

#### အသေးစိတ် ရှင်းလင်းချက်:
- `Tool(ABC)`:
  - `name`: Model သို့ ပေးမည့် tool name (ဥပမာ `list_files`).
  - `description`: Model က မည်သည့်အခါတွင် သုံးရမည်ကို နားလည်စေမည့် ရှင်းလင်းချက်။
  - `args_model`: Tool ၏ Pydantic schema model (`@abstractmethod`).
  - `input_schema`: `strict_json_schema(self.args_model)` ကို အသုံးပြု၍ Provider-strict JSON Schema ကို runtime တွင် dynamically generate လုပ်ပေးသည်။
  - `run(arguments)`: Tool ၏ core logic run ရမည့် abstract method.
  - `definition()`: Metadata dictionary ထုတ်ပေးသည့် helper method.

---

### `app/tools/call.py`
LLM က ခေါ်ဆိုရန် တောင်းဆိုလိုက်သော Tool Call record ဖြစ်သည်။

#### Source Code:
```python
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class ToolCall:
    """Provider-independent representation of a tool request.

    If the model produced arguments that could not be parsed,
    `arguments` is empty and `parse_error` explains why. The call
    is NOT executed; the error goes back to the model as an observation.
    """

    call_id: str
    tool_name: str
    arguments: dict[str, Any]
    parse_error: str | None = None
```

#### အသေးစိတ် ရှင်းလင်းချက်:
- `ToolCall`: Immutable (`frozen=True`) dataclass ဖြစ်ပြီး model က ပြန်ပို့လိုက်သော `call_id`၊ ခေါ်ဆိုလိုသော `tool_name`၊ ပေးပို့လာသော `arguments` dict နှင့် အကယ်၍ JSON syntax ပျက်ယွင်းနေပါက `parse_error` string ကို သိမ်းဆည်းသည်။
- Model ထံမှ arguments များ malformed ဖြစ်ပါက `arguments={}` ဖြစ်ပြီး `parse_error` ပါရှိသဖြင့် runtime crash မဖြစ်ဘဲ model ထံသို့ observation အဖြစ် ပြန်ပို့ပေးနိုင်သည်။

---

### `app/tools/call_parsing.py`
Model ထံမှ လာသော raw JSON argument string များကို error မတက်စေဘဲ ဘေးကင်းစွာ parse လုပ်ပေးသည့် helper module ဖြစ်သည်။

#### Source Code:
```python
import json
from typing import Any

from .call import ToolCall


def parse_tool_call(*, call_id: str, name: str, raw_arguments: str) -> ToolCall:
    """Parse provider tool-call arguments without ever raising.

    Model output is untrusted: invalid JSON or a non-object payload becomes
    a ToolCall carrying parse_error instead of crashing the run.
    """
    try:
        parsed: Any = json.loads(raw_arguments)
    except (json.JSONDecodeError, TypeError) as exc:
        return ToolCall(
            call_id=call_id,
            tool_name=name,
            arguments={},
            parse_error=f"arguments are not valid JSON: {exc}",
        )

    if not isinstance(parsed, dict):
        return ToolCall(
            call_id=call_id,
            tool_name=name,
            arguments={},
            parse_error=(
                "arguments must be a JSON object, "
                f"got {type(parsed).__name__}"
            ),
        )

    return ToolCall(call_id=call_id, tool_name=name, arguments=parsed)
```

#### အသေးစိတ် ရှင်းလင်းချက်:
- `parse_tool_call(...)`:
  - Never-raise design: Model output သည် untrusted ဖြစ်သဖြင့် `json.loads` ပျက်စီးခြင်း (`JSONDecodeError`, `TypeError`) သို့မဟုတ် JSON Array ဖြစ်နေခြင်း (`not isinstance(parsed, dict)`) တို့ ဖြစ်ပေါ်လာပါက exception မ raise ဘဲ `ToolCall(arguments={}, parse_error=...)` အဖြစ် wrap လုပ်ပေးသည်။
  - Real client (`OpenAIClient`) နှင့် Mock client (`FakeLLMClient`) နှစ်ခုစလုံးက ဤ helper ကို မျှဝေသုံးစွဲသဖြင့် production နှင့် test ပတ်ဝန်းကျင် တူညီစေသည်။

---

### `app/tools/execution.py`
Tool တစ်ခု run ပြီးသွားသောအခါ ရရှိလာသည့် execution record ဖြစ်သည်။

#### Source Code:
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

#### အသေးစိတ် ရှင်းလင်းချက်:
- `ToolExecution`: Tool အမည်၊ arguments၊ ထွက်လာသော result၊ အကယ်၍ error ရှိပါက error string နှင့် execution ကြာချိန် millisecond (`duration_ms`) တို့ ပါဝင်သည်။ `success` property က error မရှိလျှင် `True` ဖြစ်သည်။

---

### `app/tools/workspace.py`
Security boundary (Sandbox) အဖြစ် ဆောင်ရွက်ပြီး path traversal attack များကို တားဆီးပေးသည့် class ဖြစ်သည်။

#### Source Code:
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

#### အသေးစိတ် ရှင်းလင်းချက်:
- `Workspace(root)`: Root path ကို canonical absolute path အဖြစ် resolve လုပ်သည်။
- `resolve(path: str) -> Path`:
  - ပေးလာသော path (ဥပမာ `../../etc/passwd` သို့မဟုတ် `C:\Windows`) ကို root နှင့် ပေါင်းစပ်ပြီး `candidate.relative_to(self._root)` စစ်ဆေးသည်။
  - Path သည် root directory အပြင်သို့ ထွက်သွားပါက ချက်ချင်း `PermissionError("Path escapes workspace: ...")` တက်စေပြီး sandbox boundary ကို တင်းကြပ်စွာ ထိန်းသိမ်းသည်။

---

### `app/tools/schemas.py`
Pydantic v2 ကို အသုံးပြု၍ LLM ထံမှ လာသော arguments များကို validate ပြုလုပ်သည့် models များ ဖြစ်သည်။

#### Source Code:
```python
from pydantic import BaseModel, ConfigDict, Field, field_validator


class ToolArgs(BaseModel):
    """
    Base class for all tool argument models.

    Fields here are exactly what the MODEL may choose. Budget/safety
    limits (max_bytes, max_results, ...) are NOT model-controlled; they
    are tool configuration.
    """

    model_config = ConfigDict(
        extra="forbid",
        str_strip_whitespace=True,
    )


class ListFilesArgs(ToolArgs):
    path: str = Field(
        default="",
        description=(
            "Workspace-relative directory path. "
            "Use an empty string for the workspace root."
        ),
    )


class ReadFileArgs(ToolArgs):
    path: str = Field(description="Workspace-relative file path.")

    @field_validator("path")
    @classmethod
    def validate_path(cls, value: str) -> str:
        if not value:
            raise ValueError("path must not be empty")
        return value


class SearchTextArgs(ToolArgs):
    query: str = Field(description="Text to search for.")
    path: str = Field(
        default="",
        description=(
            "Workspace-relative directory or file. "
            "Use an empty string for the workspace root."
        ),
    )

    @field_validator("query")
    @classmethod
    def validate_query(cls, value: str) -> str:
        if not value:
            raise ValueError("query must not be empty")
        return value
```

#### အသေးစိတ် ရှင်းလင်းချက်:
- `ToolArgs`: LLM output သည် untrusted input ဖြစ်သဖြင့် `extra="forbid"` (သတ်မှတ်မထားသော field များ ပေးပို့လာပါက တားဆီးရန်) နှင့် `str_strip_whitespace=True` သတ်မှတ်ထားသည်။
- **Safety Policy vs Model-Controlled Args**:
  - `max_bytes`, `max_results`, `max_file_bytes` ကဲ့သို့သော safety limits များကို model-facing arguments များထဲမှ ဖယ်ထုတ်ထားပြီး Tool constructor configuration သီးသန့် အဖြစ်သာ ထားရှိသည်။ Model ကိုယ်တိုင် limit တိုးမြှင့်ခြင်း မပြုနိုင်စေရန် ဖြစ်သည်။
- `ListFilesArgs`: `path` default သည် `""` (workspace root).
- `ReadFileArgs`: `path` သည် အလွတ်မဖြစ်ရ (`validate_path`).
- `SearchTextArgs`: `query` သည် အလွတ်မဖြစ်ရ (`validate_query`).

---

### `app/tools/schema_utils.py`
Pydantic model မှ Provider Strict Mode များနှင့် ကိုက်ညီသော JSON Schema ထုတ်ပေးသည့် utility module ဖြစ်သည်။

#### Source Code:
```python
from typing import Any

from pydantic import BaseModel


def strict_json_schema(model: type[BaseModel]) -> dict[str, Any]:
    """
    Build a provider-strict JSON schema from a Pydantic model.

    Strict function-calling modes generally require:
    - additionalProperties: false
    - every property listed in `required`
    - no `title` / `default` noise

    NOTE: exact provider rules vary; verify against Groq docs.
    Nested models ($defs) are intentionally unsupported for now.
    """
    raw = model.model_json_schema()

    if "$defs" in raw:
        raise ValueError(
            f"{model.__name__}: nested models are not supported "
            "by strict_json_schema yet"
        )

    properties: dict[str, Any] = {}
    for name, spec in raw.get("properties", {}).items():
        cleaned = {
            k: v for k, v in spec.items() if k not in ("title", "default")
        }
        properties[name] = cleaned

    return {
        "type": "object",
        "properties": properties,
        "required": list(properties.keys()),
        "additionalProperties": False,
    }
```

#### အသေးစိတ် ရှင်းလင်းချက်:
- OpenAI / Groq Strict Tool Calling စည်းကမ်းချက်များနှင့် ကိုက်ညီစေရန်:
  1. `additionalProperties: False` ကို ထည့်သွင်းပေးသည်။
  2. Property အားလုံးကို `required` list ထဲသို့ ထည့်သွင်းပေးသည်။
  3. Pydantic မှ အလိုအလျောက် ထည့်သွင်းပေးသော `title` နှင့် `default` များကို ရှင်းထုတ်ပေးသည်။
  4. Unsupported ဖြစ်သော nested `$defs` ပါလာပါက ValueError ဖြင့် fail-closed စစ်ဆေးသည်။

---

### `app/tools/validation.py`
Tool arguments များ validation မအောင်မြင်ပါက model ဖတ်ရှုနားလည်နိုင်သော compact JSON observation format ထုတ်ပေးသည့် module ဖြစ်သည်။

#### Source Code:
```python
import json
from typing import Any

from pydantic import ValidationError


def format_validation_error(
    tool_name: str,
    error: ValidationError,
) -> dict[str, Any]:
    """Compact, LLM-readable description of a tool-argument failure."""
    errors: list[dict[str, Any]] = [
        {
            "field": ".".join(str(part) for part in item.get("loc", ())),
            "message": item.get("msg", "Invalid value"),
            "type": item.get("type", "validation_error"),
        }
        for item in error.errors()
    ]

    return {
        "error_type": "tool_argument_validation",
        "tool_name": tool_name,
        "message": f"Invalid arguments for tool '{tool_name}'.",
        "errors": errors,
    }


def format_validation_error_json(tool_name: str, error: ValidationError) -> str:
    return json.dumps(format_validation_error(tool_name, error))
```

#### အသေးစိတ် ရှင်းလင်းချက်:
- Pydantic ၏ ရှည်လျားသော ValidationError object မှ model အတွက် အရေးပါသည့် `field`, `message`, `type` များကိုသာ ထုတ်ယူပြီး structured error dictionary/JSON string အဖြစ် ပြောင်းပေးသည်။

---

### `app/tools/registry.py`
Tool instances များကို သိမ်းဆည်းပေးသော Registry ဖြစ်သည်။

#### Source Code:
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

#### အသေးစိတ် ရှင်းလင်းချက်:
- `register(tool)`: Tool instance ထည့်သွင်းသည်။ နာမည်တူပြီးသားရှိလျှင် `ValueError` ပြသည်။
- `get(name)`: နာမည်ဖြင့် tool ကို ပြန်ထုတ်ယူသည်။
- `definitions()`: Tool အားလုံး၏ specification list ကို ထုတ်ပေးသည်။

---

### `app/tools/executor.py`
Tool execution engine ဖြစ်ပြီး validation စစ်ဆေးခြင်း၊ အချိန်တိုင်းတာခြင်းနှင့် Error-as-Observation pattern ကို အကောင်အထည်ဖော်ထားသည်။

#### Source Code:
```python
from time import perf_counter
from typing import Any

from pydantic import ValidationError

from .execution import ToolExecution
from .registry import ToolRegistry
from .validation import format_validation_error_json


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

        def elapsed_ms() -> float:
            return (perf_counter() - started_at) * 1000

        try:
            tool = self._registry.get(tool_name)

            try:
                validated = tool.args_model.model_validate(
                    arguments
                ).model_dump()
            except ValidationError as exc:
                return ToolExecution(
                    tool_name=tool_name,
                    arguments=arguments,
                    result=None,
                    error=format_validation_error_json(tool_name, exc),
                    duration_ms=elapsed_ms(),
                )

            result = tool.run(validated)

            return ToolExecution(
                tool_name=tool_name,
                arguments=arguments,
                result=result,
                error=None,
                duration_ms=elapsed_ms(),
            )

        except Exception as exc:  # noqa: BLE001
            return ToolExecution(
                tool_name=tool_name,
                arguments=arguments,
                result=None,
                error=str(exc),
                duration_ms=elapsed_ms(),
            )
```

#### အသေးစိတ် ရှင်းလင်းချက်:
- `ToolExecutor(registry)`:
  - `ToolArgumentRegistry` ကို ဖယ်ရှားပြီး Tool တစ်ခုချင်းစီ၏ `args_model` မှတစ်ဆင့် validation စစ်ဆေးသည်။
  - **Mandatory Validation**: Validation ကို optional မဟုတ်ဘဲ အမြဲတမ်း မဖြစ်မနေ စစ်ဆေးသည် (security bypass မဖြစ်စေရန်)။
- `execute(*, tool_name, arguments)`:
  1. `perf_counter()` ဖြင့် execution time စတင်တိုင်းတာသည်။
  2. `tool.args_model.model_validate(arguments).model_dump()` ဖြင့် validate လုပ်သည်။ Validation ကျရှုံးပါက `format_validation_error_json` ဖြင့် compact JSON structured observation error ကို `ToolExecution(error=...)` ဖြင့် ပြန်ပေးသည်။
  3. Valid ဖြစ်သော dictionary ဖြင့် `tool.run(validated)` ကို execute လုပ်သည်။
  4. မည်သည့် exception တက်တက် crash မဖြစ်စေဘဲ `ToolExecution(error=str(exc))` အဖြစ် return ပြန်ပေးသည်။ ဤနည်းအားဖြင့် Error သည် Model ထံ observation အဖြစ် ပြန်ရောက်သွားပြီး Model က မိမိအမှားကို ပြန်လည်ပြင်ဆင် (self-correct) ခွင့်ရရှိစေသည်။

---

### `app/tools/list_files.py`
ဖိုင်နှင့် directory စာရင်းများကို ထုတ်ပေးသည့် Tool ဖြစ်သည်။

#### Source Code:
```python
from typing import Any

from .base import Tool
from .schemas import ListFilesArgs
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
    def args_model(self) -> type[ListFilesArgs]:
        return ListFilesArgs

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

#### အသေးစိတ် ရှင်းလင်းချက်:
- `args_model`: `ListFilesArgs` ကို သတ်မှတ်ထားသည်။
- `run(arguments)`: ပေးလိုက်သော path ကို `_workspace.resolve()` ဖြင့် စစ်ဆေးသည်။ Directory မရှိပါက `FileNotFoundError`၊ Directory မဟုတ်ပါက `NotADirectoryError` ပြသည်။ Directory အတွင်းရှိ အမည်များကို alphabet အစဉ်လိုက် sorted ပြုလုပ်ပြီး list အဖြစ် ပြန်ပေးသည်။

---

### `app/tools/read_file.py`
UTF-8 text ဖိုင်များကို ဖတ်ရှုပေးသည့် Tool ဖြစ်သည်။

#### Source Code:
```python
from typing import Any

from .base import Tool
from .schemas import ReadFileArgs
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
    def args_model(self) -> type[ReadFileArgs]:
        return ReadFileArgs

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

#### အသေးစိတ် ရှင်းလင်းချက်:
- `args_model`: `ReadFileArgs` ကို အသုံးပြုထားသည်။
- `max_bytes`: Tool constructor တွင် default 100KB သတ်မှတ်ထားပြီး context window budget မကျော်စေရန် guard အဖြစ် ဆောင်ရွက်သည်။
- `run(arguments)`: File မရှိခြင်း၊ directory ဖြစ်နေခြင်း၊ `max_bytes` ထက် ကျော်လွန်နေခြင်းနှင့် binary/non-UTF8 ဖြစ်နေခြင်းများကို စစ်ဆေးကာ error ထုတ်ပေးသည်။

---

### `app/tools/search_text.py`
Workspace အတွင်း ဖိုင်များထဲတွင် substring ရှာဖွေပေးသော Tool ဖြစ်သည်။

#### Source Code:
```python
from pathlib import Path
from typing import Any

from .base import Tool
from .schemas import SearchTextArgs
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
    def args_model(self) -> type[SearchTextArgs]:
        return SearchTextArgs

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

#### အသေးစိတ် ရှင်းလင်းချက်:
- `args_model`: `SearchTextArgs` ကို အသုံးပြုထားသည်။
- `_iter_files(directory)`: Directory တစ်ခုလုံးကို recursive search လုပ်ရာတွင် `.git` directory များကို automatically skip လုပ်သည်။
- `_search_file(...)`: Case-insensitive အနေဖြင့် စာကြောင်းတစ်ကြောင်းချင်း ရှာဖွေပြီး `line` နံပါတ်နှင့် `text` ကို စုစည်းပေးသည်။
- `run(arguments)`: File size ကန့်သတ်ချက် (`max_file_bytes = 200KB`) ထက်ကြီးသောဖိုင်များကို ကျော်သွားပြီး အများဆုံး ရလဒ် ၅၀ ခု (`max_results = 50`) အထိ ရှာဖွေပေးသည်။

---

### `app/tools/__init__.py`
Tools package ၏ module exports ဖြစ်သည်။

#### Source Code:
```python
from .base import Tool
from .call import ToolCall
from .call_parsing import parse_tool_call
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
    "parse_tool_call",
]
```

---

## 6. Agent Runtime & Control Layer (`app/agent/`)

Agent ၏ ဦးနှောက်နှင့် ထိန်းချုပ်ရေးဗဟို (Core Engine) ဖြစ်ပါသည်။ Loop, State, Guards, Budgets, Retry နှင့် Resiliency အားလုံး ပါဝင်သည်။

### `app/agent/clock.py`
Deterministic testing ပြုလုပ်နိုင်ရန် အချိန်တိုင်းတာမှု interface ဖြစ်သည်။

#### Source Code:
```python
from time import monotonic
from typing import Protocol


class Clock(Protocol):
    def now(self) -> float:
        ...


class MonotonicClock:
    def now(self) -> float:
        return monotonic()
```

#### အသေးစိတ် ရှင်းလင်းချက်:
- `Clock(Protocol)`: `now() -> float` function ပါဝင်သော protocol ဖြစ်သည်။
- `MonotonicClock`: Python ၏ `time.monotonic()` ကို အသုံးပြုသည်။ Unit test များတွင် fake time ပေးနိုင်ရန် protocol ဖြင့် ခွဲထုတ်ထားခြင်း ဖြစ်သည်။

---

### `app/agent/budget.py`
Wall-clock အချိန်နှင့် iteration budget များကို စစ်ဆေးထိန်းကျောင်းပေးသည်။

#### Source Code:
```python
from dataclasses import dataclass

from .clock import Clock


@dataclass(frozen=True)
class RuntimeBudget:
    max_iterations: int = 10
    max_wall_time_seconds: float = 60.0
    per_call_timeout_seconds: float = 30.0

    def __post_init__(self) -> None:
        if self.max_iterations < 1:
            raise ValueError(
                "max_iterations must be >= 1"
            )

        if self.max_wall_time_seconds <= 0:
            raise ValueError(
                "max_wall_time_seconds must be > 0"
            )

        if self.per_call_timeout_seconds <= 0:
            raise ValueError(
                "per_call_timeout_seconds must be > 0"
            )


class BudgetTracker:
    def __init__(
        self,
        budget: RuntimeBudget,
        clock: Clock,
    ) -> None:
        self._budget = budget
        self._clock = clock
        self._started_at = clock.now()

    def elapsed_seconds(self) -> float:
        return (
            self._clock.now()
            - self._started_at
        )

    def is_expired(self) -> bool:
        return (
            self.elapsed_seconds()
            >= self._budget.max_wall_time_seconds
        )
```

#### အသေးစိတ် ရှင်းလင်းချက်:
- `RuntimeBudget`:
  - `max_iterations`: အများဆုံး ခွင့်ပြုမည့် loop အကြိမ်ရေ (default 10).
  - `max_wall_time_seconds`: Agent တစ်ခုလုံး run ရန် ခွင့်ပြုထားသော အချိန် စက္ကန့် ၆၀။
  - `per_call_timeout_seconds`: LLM တစ်ကြိမ် call လျှင် စက္ကန့် ၃၀ timeout။
- `BudgetTracker`:
  - `elapsed_seconds()`: စတင်ချိန်မှစ၍ ကုန်လွန်သွားသော စက္ကန့်ကို တွက်သည်။
  - `is_expired()`: Wall-clock time ကျော်လွန်သွားပြီလား boolean ပြန်ပေးသည်။

---

### `app/agent/usage.py`
Token usage ကို provider မျိုးစုံမှ unified structure အဖြစ် ပြောင်းလဲပေးသည်။

#### Source Code:
```python
from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class Usage:
    """Provider-independent token usage for one LLM call."""

    input_tokens: int = 0
    output_tokens: int = 0

    @property
    def total_tokens(self) -> int:
        return self.input_tokens + self.output_tokens

    def __add__(self, other: Usage) -> Usage:
        return Usage(
            input_tokens=self.input_tokens + other.input_tokens,
            output_tokens=self.output_tokens + other.output_tokens,
        )


def _first_int(obj: Any, *names: str) -> int | None:
    for name in names:
        value = getattr(obj, name, None)
        if isinstance(value, int) and not isinstance(value, bool):
            return value
    return None


def extract_usage(response: Any) -> Usage | None:
    """
    Normalise provider usage into Usage.

    Returns None (NOT zero) when the provider did not report usage.
    Silent zero would make budget enforcement fail open.

    Supports Responses-API naming (input_tokens/output_tokens) and
    Chat-Completions naming (prompt_tokens/completion_tokens).
    """
    raw = getattr(response, "usage", None)
    if raw is None:
        return None

    input_tokens = _first_int(raw, "input_tokens", "prompt_tokens")
    output_tokens = _first_int(raw, "output_tokens", "completion_tokens")

    if input_tokens is None or output_tokens is None:
        return None

    return Usage(input_tokens=input_tokens, output_tokens=output_tokens)
```

#### အသေးစိတ် ရှင်းလင်းချက်:
- `Usage`: `input_tokens` နှင့် `output_tokens` ပါဝင်သော immutable dataclass ဖြစ်ပြီး `+` operator ဖြင့် တိုက်ရိုက် ပေါင်းစပ်နိုင်သည်။
- `extract_usage(response)`:
  - Responses API format (`input_tokens`/`output_tokens`) ရော Chat Completions format (`prompt_tokens`/`completion_tokens`) ပါ auto-detect လုပ်ပေးသည်။
  - **Fail Closed Principle**: Usage data မပါလာပါက `0` မပေးဘဲ `None` ပြန်ပေးသည်။ အကယ်၍ `0` ပေးမိပါက Token budget guard က မသိရှိဘဲ budget ကန့်သတ်ချက်ကို ကျော်လွန်သွားနိုင်သောကြောင့် ဖြစ်သည်။

---

### `app/agent/cost.py`
Model pricing၊ token budget များနှင့် run တစ်ခုလုံး၏ usage report များကို တွက်ချက်သည့် layer ဖြစ်သည်။

#### Source Code:
```python
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .usage import Usage


@dataclass(frozen=True)
class ModelPricing:
    """USD per 1M tokens. Supplied via config, never hardcoded."""

    input_usd_per_mtok: float
    output_usd_per_mtok: float

    def __post_init__(self) -> None:
        if self.input_usd_per_mtok < 0 or self.output_usd_per_mtok < 0:
            raise ValueError("pricing must be >= 0")

    def cost_usd(self, usage: Usage) -> float:
        return (
            usage.input_tokens * self.input_usd_per_mtok
            + usage.output_tokens * self.output_usd_per_mtok
        ) / 1_000_000


@dataclass(frozen=True)
class TokenBudget:
    max_total_tokens: int | None = None
    max_cost_usd: float | None = None

    def __post_init__(self) -> None:
        if self.max_total_tokens is not None and self.max_total_tokens < 1:
            raise ValueError("max_total_tokens must be >= 1")
        if self.max_cost_usd is not None and self.max_cost_usd <= 0:
            raise ValueError("max_cost_usd must be > 0")


@dataclass(frozen=True)
class UsageRecord:
    call_index: int  # 1-based
    usage: Usage | None  # None = provider did not report


class UsageTracker:
    """Accumulates per-call usage for a single agent run."""

    def __init__(self, pricing: ModelPricing | None = None) -> None:
        self._pricing = pricing
        self._records: list[UsageRecord] = []

    def record(self, usage: Usage | None) -> None:
        self._records.append(
            UsageRecord(call_index=len(self._records) + 1, usage=usage)
        )

    @property
    def calls(self) -> int:
        return len(self._records)

    @property
    def unreported_calls(self) -> int:
        return sum(1 for r in self._records if r.usage is None)

    @property
    def total(self) -> Usage:
        total = Usage()
        for record in self._records:
            if record.usage is not None:
                total = total + record.usage
        return total

    def cost_usd(self) -> float | None:
        if self._pricing is None:
            return None
        return self._pricing.cost_usd(self.total)

    def exceeded(self, budget: TokenBudget) -> str | None:
        """Return the reason the budget is exhausted, or None."""
        if self.unreported_calls:
            return "usage_unreported"  # fail closed

        if (
            budget.max_total_tokens is not None
            and self.total.total_tokens >= budget.max_total_tokens
        ):
            return "max_total_tokens"

        cost = self.cost_usd()
        if (
            budget.max_cost_usd is not None
            and cost is not None
            and cost >= budget.max_cost_usd
        ):
            return "max_cost_usd"

        return None

    def report(self) -> dict[str, Any]:
        cumulative = 0
        per_call: list[dict[str, Any]] = []

        for record in self._records:
            if record.usage is None:
                per_call.append(
                    {"call": record.call_index, "input_tokens": None,
                     "output_tokens": None, "cumulative_total": cumulative}
                )
                continue
            cumulative += record.usage.total_tokens
            per_call.append(
                {
                    "call": record.call_index,
                    "input_tokens": record.usage.input_tokens,
                    "output_tokens": record.usage.output_tokens,
                    "cumulative_total": cumulative,
                }
            )

        total = self.total
        cost = self.cost_usd()

        return {
            "calls": self.calls,
            "unreported_calls": self.unreported_calls,
            "input_tokens": total.input_tokens,
            "output_tokens": total.output_tokens,
            "total_tokens": total.total_tokens,
            "cost_usd": round(cost, 6) if cost is not None else None,
            "per_call": per_call,
        }
```

#### အသေးစိတ် ရှင်းလင်းချက်:
- `ModelPricing`: Tokens ၁ သန်းနှုန်းထားဖြင့် ဒေါ်လာတွက်ပေးသည်။ Hardcode မထားဘဲ configuration မှသာ ယူသည်။
- `TokenBudget`: အများဆုံး tokens အရေအတွက် (`max_total_tokens`) သို့မဟုတ် အများဆုံးကုန်ကျစရိတ် (`max_cost_usd`) သတ်မှတ်နိုင်သည်။
- `UsageTracker`:
  - Call တိုင်း၏ usage ကို မှတ်တမ်းတင်သည်။
  - `exceeded(budget)`: Token အရေအတွက် ကျော်လွန်ခြင်း၊ ဒေါ်လာ ကုန်ကျစရိတ် ကျော်လွန်ခြင်း သို့မဟုတ် usage မရရှိ၍ fail closed ဖြစ်ခြင်း စသည့် အကြောင်းရင်း string ကို ပြန်ပေးသည်။
  - `report()`: Terminal တွင် ပြသနိုင်ရန် clean summary dictionary ကို ပြန်ပေးသည်။

---

### `app/agent/decision.py`
Structured output အသုံးပြုသည့်အခါ LLM ထံမှ လာသော ဆုံးဖြတ်ချက်ကို တိကျစွာ enforce လုပ်သော Pydantic model ဖြစ်သည်။

#### Source Code:
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

#### အသေးစိတ် ရှင်းလင်းချက်:
- `Decision` model သည် Model ၏ action ၂ မျိုးကို တိကျစွာ ခွဲခြားထားသည်:
  1. `TOOL_CALL`: `tool_name` နှင့် `arguments` မဖြစ်မနေပါရမည်၊ `final_answer` လုံးဝမပါရ။
  2. `FINAL_ANSWER`: `final_answer` မဖြစ်မနေပါရမည်၊ `tool_name` နှင့် `arguments` လုံးဝမပါရ။
- မဆိုင်သော field များ ပါလာခြင်းကို `extra="forbid"` ဖြင့် ပိတ်ပင်ထားသည်။

---

### `app/agent/decision_schema.py`
Decision model ၏ JSON Schema generator ဖြစ်သည်။

#### Source Code:
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

---

### `app/agent/structured_output.py`
JSON string သို့မဟုတ် dict payload မှ `Decision` အဖြစ် parse နှင့် validate ပြုလုပ်ပေးသည့် module ဖြစ်သည်။

#### Source Code:
```python
import json
from typing import Any, Protocol

from pydantic import ValidationError

from .decision import Decision


class StructuredOutputError(Exception):
    """Raised when structured LLM output cannot be parsed or validated."""


class StructuredDecisionClient(Protocol):
    """Provider-facing abstraction for structured decision generation."""

    def generate_decision(
        self,
        prompt: str,
        schema: dict[str, Any],
    ) -> dict[str, Any]:
        ...


def parse_prompt_json(raw_output: str) -> Decision:
    """Parse JSON produced by a prompt-based structured-output strategy."""
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
    """Validate a provider-produced structured payload."""
    try:
        return Decision.model_validate(payload)
    except ValidationError as exc:
        raise StructuredOutputError(
            f"Decision schema validation failed: {exc}"
        ) from exc
```

---

### `app/agent/validation_errors.py`
Structured output validation failures များကို LLM ထံ observation အဖြစ် ပြန်ပို့နိုင်သော format သို့ ပြောင်းပေးသည့် helper function ဖြစ်သည်။ (Tool argument validation error formatter ကိုမူ `app/tools/validation.py` တွင် ပေါင်းစည်းထားသည်)။

#### Source Code:
```python
from typing import Any


def format_structured_output_error(
    error: Exception,
) -> dict[str, Any]:
    """
    Convert structured-output failures into a compact
    observation that can be sent back to the LLM.
    """

    return {
        "success": False,
        "error_type": "structured_output_validation",
        "message": str(error),
    }
```

#### အသေးစိတ် ရှင်းလင်းချက်:
- `format_structured_output_error(error)`: Decision schema parse မရခြင်း သို့မဟုတ် schema validation ကျရှုံးခြင်းများအတွက် LLM ထံ ပေးပို့နိုင်မည့် structured observation dictionary အဖြစ် serialize လုပ်ပေးသည်။

---

### `app/agent/decision_recovery.py`
Malformed structured output ဖြစ်ပေါ်ပါက safe recovery ပြုလုပ်ပေးသည့် helper class ဖြစ်သည်။

#### Source Code:
```python
from typing import Any

from .structured_output import (
    StructuredDecisionClient,
    StructuredOutputError,
    validate_structured_payload,
)
from .validation_errors import (
    format_structured_output_error,
)


class DecisionRecovery:
    def __init__(
        self,
        client: StructuredDecisionClient,
        schema: dict[str, Any],
    ) -> None:
        self._client = client
        self._schema = schema

    def generate(
        self,
        prompt: str,
    ):
        try:
            payload = self._client.generate_decision(
                prompt,
                self._schema,
            )

            decision = validate_structured_payload(
                payload
            )

            return decision, None

        except StructuredOutputError as exc:
            return (
                None,
                format_structured_output_error(exc),
            )
```

---

### `app/agent/history.py`
Tool executions စာရင်းအားလုံးကို run တစ်ခုလုံးအတွက် မှတ်တမ်းတင်သိမ်းဆည်းပေးသည်။

#### Source Code:
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

---

### `app/agent/llm_errors.py`
LLM API exceptions များကို transient error လား permanent error လား ခွဲခြားပေးသည့် classifier ဖြစ်သည်။

#### Source Code:
```python
from __future__ import annotations

import openai

from .retry import ErrorKind

_TRANSIENT: tuple[type[Exception], ...] = (
    openai.RateLimitError,
    openai.APITimeoutError,
    openai.APIConnectionError,
    openai.InternalServerError,
)


def classify_llm_error(error: Exception) -> ErrorKind:
    """
    Map an LLM-call exception to a retry classification.

    Unknown errors are PERMANENT: retrying something we do not
    understand is worse than failing loudly.

    NOTE: APITimeoutError subclasses APIConnectionError in the SDK;
    both are listed explicitly so intent survives a refactor.
    """
    if isinstance(error, _TRANSIENT):
        return ErrorKind.TRANSIENT
    return ErrorKind.PERMANENT
```

#### အသေးစိတ် ရှင်းလင်းချက်:
- `_TRANSIENT`: RateLimitError, APITimeoutError, APIConnectionError, InternalServerError တို့ ဖြစ်ပြီး retry ပြုလုပ်ပါက ပြေလည်နိုင်သည့် ယာယီအမှားများ ဖြစ်သည်။
- **Fail Loud Principle**: မသိသော error များအားလုံးကို `PERMANENT` အဖြစ် သတ်မှတ်သည်။ အကြောင်းရင်းမသိဘဲ မျက်စိစုံမှိတ် retry လုပ်ခြင်းသည် resources နှင့် budget များကို အလဟဿကုန်စေသောကြောင့် ဖြစ်သည်။

---

### `app/agent/retry.py`
Exponential backoff retry policy ကို implement လုပ်ထားသည်။

#### Source Code:
```python
from dataclasses import dataclass
from enum import Enum


class ErrorKind(str, Enum):
    TRANSIENT = "transient"
    PERMANENT = "permanent"


@dataclass(frozen=True)
class RetryDecision:
    should_retry: bool
    delay_seconds: float
    reason: str


@dataclass(frozen=True)
class RetryPolicy:
    max_attempts: int = 3
    base_delay_seconds: float = 0.5
    max_delay_seconds: float = 8.0

    def __post_init__(self) -> None:
        if self.max_attempts < 1:
            raise ValueError("max_attempts must be >= 1")

        if self.base_delay_seconds < 0:
            raise ValueError(
                "base_delay_seconds must be >= 0"
            )

        if self.max_delay_seconds < 0:
            raise ValueError(
                "max_delay_seconds must be >= 0"
            )

    def classify(self, error_kind: ErrorKind) -> bool:
        return error_kind == ErrorKind.TRANSIENT

    def decide(
        self,
        *,
        attempt: int,
        error_kind: ErrorKind,
    ) -> RetryDecision:
        if attempt < 1:
            raise ValueError("attempt must be >= 1")

        if not self.classify(error_kind):
            return RetryDecision(
                should_retry=False,
                delay_seconds=0.0,
                reason="permanent error",
            )

        if attempt >= self.max_attempts:
            return RetryDecision(
                should_retry=False,
                delay_seconds=0.0,
                reason="retry budget exhausted",
            )

        delay = min(
            self.base_delay_seconds * (2 ** (attempt - 1)),
            self.max_delay_seconds,
        )

        return RetryDecision(
            should_retry=True,
            delay_seconds=delay,
            reason="transient error",
        )
```

#### အသေးစိတ် ရှင်းလင်းချက်:
- `decide(attempt, error_kind)`:
  - Permanent error ဖြစ်လျှင် `should_retry=False`.
  - သတ်မှတ်ကြိမ်ရေ (`max_attempts`) ကျော်လွန်ပါက `should_retry=False`.
  - Transient ဖြစ်ပါက `delay = min(base_delay * (2 ** (attempt - 1)), max_delay)` အတိုင်း တွက်ချက်ပြီး စောင့်ဆိုင်းစေသည်။

---

### `app/agent/resilient_client.py`
LLM Client ကို retry နှင့် error recovery ဖြင့် wrap ပေးသော decorator client ဖြစ်သည်။

#### Source Code:
```python
from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from app.tools import Tool, ToolCall

from .llm_errors import classify_llm_error
from .retry import ErrorKind, RetryPolicy


class LLMCallFailed(Exception):
    """Raised when an LLM call fails permanently or exhausts retries."""

    def __init__(self, message: str, *, attempts: int, kind: ErrorKind) -> None:
        super().__init__(message)
        self.attempts = attempts
        self.kind = kind


class DeadlineExceeded(Exception):
    """Raised when the run deadline expires while waiting to retry."""


@dataclass(frozen=True)
class AttemptRecord:
    attempt: int
    error: str
    kind: ErrorKind
    delay_seconds: float


class ResilientClient:
    """
    Retry decorator around any ToolCallingClient.

    Only the LLM call is retried. Tool execution is NOT retried here:
    tools may have side effects; their failures go back to the model.
    """

    def __init__(
        self,
        inner: Any,
        policy: RetryPolicy,
        *,
        sleep: Callable[[float], None] = time.sleep,
        classify: Callable[[Exception], ErrorKind] = classify_llm_error,
    ) -> None:
        self._inner = inner
        self._policy = policy
        self._sleep = sleep
        self._deadline_expired: Callable[[], bool] | None = None
        self._classify = classify
        self.attempt_log: list[AttemptRecord] = []

    def set_deadline_check(self, check: Callable[[], bool] | None) -> None:
        """Bind the current run's deadline. Called by AgentLoop at run start."""
        self._deadline_expired = check
        self.attempt_log = []

    def respond_with_tools(
        self,
        *,
        conversation: list[dict[str, Any]],
        tools: list[Tool],
    ) -> tuple[Any, list[ToolCall]]:
        attempt = 1
        while True:
            try:
                return self._inner.respond_with_tools(
                    conversation=conversation, tools=tools
                )
            except Exception as exc:  # noqa: BLE001 - classified below
                kind = self._classify(exc)
                decision = self._policy.decide(
                    attempt=attempt, error_kind=kind)

                self.attempt_log.append(
                    AttemptRecord(
                        attempt=attempt,
                        error=f"{type(exc).__name__}: {exc}",
                        kind=kind,
                        delay_seconds=decision.delay_seconds,
                    )
                )

                if not decision.should_retry:
                    raise LLMCallFailed(
                        f"LLM call failed ({decision.reason}) "
                        f"after {attempt} attempt(s): {exc}",
                        attempts=attempt,
                        kind=kind,
                    ) from exc

                if self._deadline_expired is not None and self._deadline_expired():
                    raise DeadlineExceeded(
                        "run deadline expired while retrying LLM call"
                    ) from exc

                self._sleep(decision.delay_seconds)
                attempt += 1
```

#### အသေးစိတ် ရှင်းလင်းချက်:
- **အရေးကြီးသော Design Decision**: LLM call ကိုသာ retry လုပ်သည်၊ Tool execution ကို retry မလုပ်ပါ။ (Tool များသည် side effects ရှိနိုင်ပြီး ပျက်စီးပါက LLM ထံ observation အဖြစ်သာ ပြန်ပို့ရမည်)။
- `set_deadline_check(check)`: `AgentLoop.run()` စတင်ချိန်တိုင်း runtime ၏ deadline check callback ကို bind လုပ်ပေးပြီး `attempt_log` ကို run အသစ်အတွက် reset လုပ်ပေးသည်။ (Client instance ကို reuse လုပ်သော်လည်း run တစ်ခုနှင့်တစ်ခု state မရောနှောစေပါ)။
- Retry loop ထဲတွင် overall run deadline ကျော်မကျော် စစ်ဆေးပြီး ကျော်ပါက `DeadlineExceeded` raise လုပ်သည်။
- Attempt တိုင်းကို `attempt_log` ထဲတွင် မှတ်တမ်းတင်ထားသည်။

---

### `app/agent/loop_guard.py`
Agent များတွင် မကြာခဏ ဖြစ်တတ်သော infinite repetitive tool calling loop ကို တားဆီးပေးသည်။

#### Source Code:
```python
import json
from collections import Counter
from typing import Any


def call_fingerprint(
    tool_name: str,
    arguments: dict[str, Any],
) -> str:
    """
    Return a stable string fingerprint for a tool call.

    Argument order is normalised so that two dicts with
    the same keys/values always produce the same fingerprint.
    """
    canonical = json.dumps(
        arguments,
        sort_keys=True,
        ensure_ascii=False,
    )
    return f"{tool_name}:{canonical}"


class LoopGuard:
    def __init__(
        self,
        max_repeated_calls: int = 3,
    ) -> None:
        if max_repeated_calls < 1:
            raise ValueError(
                "max_repeated_calls must be >= 1"
            )

        self._max_repeated_calls = (
            max_repeated_calls
        )

        self._counts: Counter[str] = Counter()

    def record(self, fingerprint: str) -> bool:
        """
        Record a call fingerprint.

        Returns True when the repetition limit
        has been reached.
        """
        self._counts[fingerprint] += 1

        return (
            self._counts[fingerprint]
            >= self._max_repeated_calls
        )
```

#### အသေးစိတ် ရှင်းလင်းချက်:
- `call_fingerprint(...)`: Tool name နှင့် arguments dict ကို `sort_keys=True` ဖြင့် canonical JSON string ပြုလုပ်ကာ fingerprint ထုတ်ပေးသည်။ Dict key အစီအစဉ် ကွဲပြားသော်လည်း တူညီသော fingerprint ရရှိစေသည်။
- `LoopGuard.record(fp)`: Fingerprint တစ်ခုကို အကြိမ်ရေ မှတ်သားပြီး သတ်မှတ်ထားသော `max_repeated_calls` (ဥပမာ 3 ကြိမ်) ရောက်ပါက `True` ပြန်ပေး၍ runtime loop ကို ရပ်တန့်စေသည်။

---

### `app/agent/state.py`
Agent ၏ Lifecycle Status နှင့် Runtime State ကို ထိန်းသိမ်းသော model ဖြစ်သည်။

#### Source Code:
```python
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from .cost import UsageTracker
from .history import ExecutionHistory


class AgentStatus(str, Enum):
    RUNNING = "running"
    COMPLETED = "completed"
    MAX_ITERATIONS = "max_iterations"
    TIMEOUT = "timeout"
    LOOP_DETECTED = "loop_detected"
    TOKEN_BUDGET_EXCEEDED = "token_budget_exceeded"
    LLM_FAILED = "llm_failed"


@dataclass
class AgentState:
    conversation: list[dict[str, Any]] = field(default_factory=list)
    iteration: int = 0
    status: AgentStatus = AgentStatus.RUNNING
    final_response: str | None = None
    error: str | None = None
    history: ExecutionHistory = field(default_factory=ExecutionHistory)
    usage: UsageTracker = field(default_factory=UsageTracker)

    @property
    def is_finished(self) -> bool:
        return self.status != AgentStatus.RUNNING
```

#### အသေးစိတ် ရှင်းလင်းချက်:
- `AgentStatus`: Agent ရပ်တန့်သွားနိုင်သည့် အခြေအနေများ (အမြဲရှင်းလင်းပြတ်သားသော Terminal status များ):
  - `RUNNING`: လည်ပတ်နေဆဲ။
  - `COMPLETED`: Model က အောင်မြင်စွာ final answer ပေးခဲ့သည်။
  - `MAX_ITERATIONS`: Iteration ကန့်သတ်ချက် ပြည့်သွားသည်။
  - `TIMEOUT`: Wall-clock အချိန် ကုန်ဆုံးသွားသည်။
  - `LOOP_DETECTED`: တူညီသော tool call ထပ်တလဲလဲ ခေါ်နေသည်ကို မိသွားသည်။
  - `TOKEN_BUDGET_EXCEEDED`: သတ်မှတ် token သို့မဟုတ် cost budget ကျော်လွန်သွားသည်။
  - `LLM_FAILED`: LLM API မအောင်မြင်ခြင်း (retries ကုန်ဆုံးခြင်း သို့မဟုတ် permanent error).
- `AgentState.is_finished`: Status က `RUNNING` မဟုတ်တော့ပါက `True` ဖြစ်သည်။

---

### `app/agent/loop.py`
Runtime တစ်ခုလုံး၏ Core Orchestration Engine ဖြစ်သည်။ LLM ဆုံးဖြတ်ချက်များ ရယူခြင်း၊ Guard စစ်ဆေးခြင်း၊ Tool run ခြင်းနှင့် State update လုပ်ခြင်းများကို ပေါင်းစပ်မောင်းနှင်ပေးသည်။

#### Source Code:
```python
import json
from collections.abc import Callable
from typing import Any, Protocol

from app.tools import Tool, ToolCall, ToolExecutor, ToolRegistry

from .budget import BudgetTracker, RuntimeBudget
from .clock import Clock, MonotonicClock
from .cost import ModelPricing, TokenBudget, UsageTracker
from .history import ExecutionRecord
from .loop_guard import LoopGuard, call_fingerprint
from .resilient_client import DeadlineExceeded, LLMCallFailed
from .state import AgentState, AgentStatus
from .usage import extract_usage


class ToolCallingClient(Protocol):
    def respond_with_tools(
        self,
        *,
        conversation: list[dict[str, Any]],
        tools: list[Tool],
    ) -> tuple[Any, list[ToolCall]]:
        ...


class AgentLoop:
    """Orchestrates LLM decisions and tool execution.

    Guard order per iteration
    ─────────────────────────
    1. wall-clock budget   → TIMEOUT
    2. iteration budget    → MAX_ITERATIONS
    3. LLM call
    4. record usage
    5. final answer?       → COMPLETED (accepted even if over token budget)
    6. token budget        → TOKEN_BUDGET_EXCEEDED (before any side effect)
    7. loop-guard check    → LOOP_DETECTED (before execution)
    8. tool execution
    """

    def __init__(
        self,
        client: ToolCallingClient,
        registry: ToolRegistry,
        executor: ToolExecutor,
        max_iterations: int = 10,
        runtime_budget: RuntimeBudget | None = None,
        clock: Clock | None = None,
        loop_guard_factory: Callable[[], LoopGuard] | None = None,
        token_budget: TokenBudget | None = None,
        pricing: ModelPricing | None = None,
    ) -> None:
        if (
            token_budget is not None
            and token_budget.max_cost_usd is not None
            and pricing is None
        ):
            raise ValueError(
                "token_budget.max_cost_usd requires pricing to be configured"
            )

        self._client = client
        self._registry = registry
        self._executor = executor
        self._max_iterations = max_iterations
        self._runtime_budget = runtime_budget
        self._clock: Clock = clock or MonotonicClock()
        self._loop_guard_factory = loop_guard_factory
        self._token_budget = token_budget
        self._pricing = pricing

    def run(self, user_prompt: str) -> AgentState:
        state = AgentState(
            conversation=[{"role": "user", "content": user_prompt}],
            usage=UsageTracker(self._pricing),
        )

        tracker = (
            BudgetTracker(self._runtime_budget, self._clock)
            if self._runtime_budget is not None
            else None
        )
        guard = (
            self._loop_guard_factory()
            if self._loop_guard_factory is not None
            else None
        )

        set_deadline = getattr(self._client, "set_deadline_check", None)
        if callable(set_deadline):
            set_deadline(tracker.is_expired if tracker is not None else None)

        while not state.is_finished:
            if tracker is not None and tracker.is_expired():
                state.status = AgentStatus.TIMEOUT
                break

            if state.iteration >= self._max_iterations:
                state.status = AgentStatus.MAX_ITERATIONS
                break
            try:
                response, tool_calls = self._client.respond_with_tools(
                    conversation=state.conversation,
                    tools=self._registry.list(),
                )
            except DeadlineExceeded:
                state.status = AgentStatus.TIMEOUT
                break
            except LLMCallFailed as exc:
                state.status = AgentStatus.LLM_FAILED
                state.error = str(exc)
                break

            state.usage.record(extract_usage(response))
            state.conversation.extend(response.output)

            if not tool_calls:
                state.final_response = response.output_text
                state.status = AgentStatus.COMPLETED
                break

            if self._token_budget_exhausted(state):
                break

            self._process_tool_calls(tool_calls, state, guard)

            state.iteration += 1

        return state

    def _token_budget_exhausted(self, state: AgentState) -> bool:
        if self._token_budget is None:
            return False

        reason = state.usage.exceeded(self._token_budget)
        if reason is None:
            return False

        state.status = AgentStatus.TOKEN_BUDGET_EXCEEDED
        state.error = f"Token budget exceeded: {reason}"
        return True

    def _process_tool_calls(
        self,
        tool_calls: list[ToolCall],
        state: AgentState,
        guard: LoopGuard | None,
    ) -> None:
        for tool_call in tool_calls:
            if tool_call.parse_error is not None:
                self._record_parse_failure(tool_call, state)
                continue

            if guard is not None:
                fp = call_fingerprint(tool_call.tool_name, tool_call.arguments)
                if guard.record(fp):
                    state.status = AgentStatus.LOOP_DETECTED
                    return

            if state.is_finished:
                return

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

            output: dict[str, Any] = (
                {"success": True, "result": execution.result}
                if execution.success
                else {"success": False, "error": execution.error}
            )

            state.conversation.append(
                {
                    "type": "function_call_output",
                    "call_id": tool_call.call_id,
                    "output": json.dumps(output, default=str),
                }
            )

    def _record_parse_failure(self, tool_call: ToolCall, state: AgentState) -> None:
        error = f"Malformed tool call arguments: {tool_call.parse_error}"

        state.history.add(
            ExecutionRecord(
                tool_name=tool_call.tool_name,
                arguments={},
                success=False,
                result=None,
                error=error,
                duration_ms=0.0,
            )
        )
        state.conversation.append(
            {
                "type": "function_call_output",
                "call_id": tool_call.call_id,
                "output": json.dumps({"success": False, "error": error}),
            }
        )
```

#### အသေးစိတ် ရှင်းလင်းချက်:
- **Per-Run State Isolation (Clean Architecture)**:
  - `AgentLoop` constructor သည် `runtime_budget`, `clock`, `loop_guard_factory` များကို config အဖြစ်သာ လက်ခံသည်။
  - Run တစ်ခုချင်းစီ (`run()`) တွင် `BudgetTracker` နှင့် `LoopGuard` instance အသစ်များကို သီးခြား instantiate လုပ်ပေးသောကြောင့် run တစ်ခု၏ state သည် နောက် run များထံသို့ leak မဖြစ်တော့ပါ။
  - Run စတင်ချိန်တွင် resilient client ၏ `set_deadline_check()` သို့ run-local tracker ၏ `is_expired` callback ကို ချိတ်ဆက်ပေးသည်။
- `run(user_prompt: str) -> AgentState`:
  - စတင်ချိန်တွင် prompt ကို conversation သို့ ထည့်သွင်းပြီး `UsageTracker` ကို မောင်းနှင်သည်။
  - `while not state.is_finished` loop ပတ်သည်။
  - Iteration အစတွင် Wall-clock timeout နှင့် Max iterations ကို စစ်ဆေးသည်။
  - `ResilientClient` မှတစ်ဆင့် LLM call ပြုလုပ်သည်။ LLM call မအောင်မြင်ပါက `LLM_FAILED` သတ်မှတ်သည်။
  - Token usage ကို record လုပ်ပြီး response ကို conversation သို့ append လုပ်သည်။
  - Tool call မရှိပါက `final_response` သတ်မှတ်ပြီး `COMPLETED` အဖြစ် ပြီးဆုံးသည်။
  - Tool call ရှိပါက tool မ run မီ token budget စစ်ဆေးသည်။ Token budget ပြည့်နေပါက `TOKEN_BUDGET_EXCEEDED` ဖြင့် tool execution မလုပ်ဘဲ ရပ်တန့်သည်။
  - `_process_tool_calls()` ထဲတွင်:
    1. **Parse Error Handling**: Provider ထံမှ malformed tool call arguments (`parse_error != None`) ရောက်လာပါက loop guard သို့မဟုတ် executor ထံသို့မပို့ဘဲ `_record_parse_failure()` ဖြင့် observation JSON error ပြန်ပို့ကာ model အား self-correct လုပ်ခွင့်ပေးသည်။
    2. **Loop Guard**: `LoopGuard` ဖြင့် repetitive call ရှိမရှိ စစ်ဆေးသည်။ မရှိပါက `ToolExecutor` ဖြင့် run ကာ ရလဒ်/error ကို history သို့ မှတ်တမ်းတင်ပြီး conversation ထဲသို့ output block ထည့်သွင်းပေးသည်။

---

### `app/agent/__init__.py`
Agent sub-package ၏ Public API exports အပြည့်အစုံ ဖြစ်သည်။

#### Source Code:
```python
from .decision import Decision, DecisionAction
from .decision_schema import decision_json_schema
from .history import ExecutionHistory, ExecutionRecord
from .loop import AgentLoop
from .state import AgentState, AgentStatus
from .structured_output import (
    StructuredOutputError,
    parse_prompt_json,
    validate_structured_payload,
)
from .validation_errors import format_structured_output_error
from .retry import ErrorKind, RetryDecision, RetryPolicy
from .decision_recovery import DecisionRecovery
from .budget import RuntimeBudget, BudgetTracker
from .clock import Clock, MonotonicClock
from .loop_guard import LoopGuard, call_fingerprint
from .usage import Usage, extract_usage
from .cost import ModelPricing, TokenBudget, UsageTracker
from .llm_errors import classify_llm_error
from .resilient_client import LLMCallFailed, DeadlineExceeded, AttemptRecord, ResilientClient

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
    "format_structured_output_error",
    "parse_prompt_json",
    "validate_structured_payload",
    "ErrorKind",
    "RetryDecision",
    "RetryPolicy",
    "DecisionRecovery",
    "RuntimeBudget",
    "BudgetTracker",
    "Clock",
    "MonotonicClock",
    "LoopGuard",
    "Usage",
    "extract_usage",
    "ModelPricing",
    "TokenBudget",
    "UsageTracker",
    "classify_llm_error",
    "LLMCallFailed",
    "DeadlineExceeded",
    "AttemptRecord",
    "ResilientClient",
]
```

---

## 7. Core Design Principles & Takeaways

1. **No External Agent Frameworks**:
   - LangChain, LangGraph သို့မဟုတ် အခြား dynamic library များကို မသုံးဘဲ Python core standard libraries နှင့် Official SDK ဖြင့်သာ direct implementation ပြုလုပ်ထားသောကြောင့် runtime သည် predictable ဖြစ်ပြီး debug လုပ်ရလွယ်ကူသည်။
2. **Error as Observation**:
   - Tool execution ကျရှုံးမှုများ (validation error, file not found, permission error) သည် runtime ကို crash မဖြစ်စေပါ။ အမှားကို JSON observation အဖြစ် model ထံ ပြန်ပို့ပေးပြီး model က self-correct လုပ်ရန် အခွင့်အရေး ရရှိသည်။
3. **Decoupled Resiliency (LLM-only Retry)**:
   - LLM call ကိုသာ retry လုပ်သည် (Read-only network call ဖြစ်သောကြောင့်). Tool execution များကိုမူ side-effects ရှိနိုင်သဖြင့် blind retry လုံးဝမလုပ်ဘဲ model ထံ error အဖြစ်သာ အကြောင်းကြားသည်။
4. **Deterministic Guard Order**:
   - Wall-clock -> Max Iterations -> LLM Call -> Usage Record -> Final Answer -> Token Budget -> Loop Guard -> Tool Execution. ဤ guard pipeline သည် agent ကို runaway loops များ၊ infinite token burn များနှင့် hanging threads များမှ ကာကွယ်ပေးသည်။
5. **Fail-Closed Budgeting**:
   - Provider က token usage မပို့ပါက `0` မပေးဘဲ `None` သတ်မှတ်ကာ `usage_unreported` အဖြစ် fail-closed ပြုလုပ်ပြီး budget security ကို အာမခံသည်။
6. **Sandboxed Workspace**:
   - `Workspace.resolve()` သည် path traversal attack များကို root boundary ဖြင့် ကာကွယ်ပေးထားသည်။
