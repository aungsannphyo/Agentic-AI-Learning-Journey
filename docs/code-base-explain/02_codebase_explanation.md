# Agent Runtime — In-Depth Codebase Explanation

ဤစာတမ်းသည် **Agent Runtime** codebase အတွင်းရှိ Module, Class, Function တစ်ခုချင်းစီ၏ တာဝန်၊ အတွင်းပိုင်းအလုပ်လုပ်ပုံ၊ Design Decisions များနှင့် Test Suite Architecture တို့ကို အသေးစိတ် စနစ်တကျ ရှင်းပြထားသော နည်းပညာလက်စွဲ ဖြစ်ပါသည်။

---

## မာတိကာ (Table of Contents)

1. [Root & Entry Point Layer](#1-root--entry-point-layer)
   - [`app/main.py`](#appmainpy)
   - [`app/trace_view.py`](#apptrace_viewpy)
   - [`conftest.py`](#conftestpy)
2. [LLM Subsystem Layer (`app/llm/`)](#2-llm-subsystem-layer-appllm)
   - [`app/llm/types.py`](#appllmtypespy)
   - [`app/llm/errors.py`](#appllmerrorspy)
   - [`app/llm/retry.py`](#appllmretrypy)
   - [`app/llm/llm_errors.py`](#appllmllm_errorspy)
   - [`app/llm/client.py`](#appllmclientpy)
   - [`app/llm/openai_client.py`](#appllmopenai_clientpy)
   - [`app/llm/fake_client.py`](#appllmfake_clientpy)
   - [`app/llm/resilient_client.py`](#appllmresilient_clientpy)
   - [`app/llm/openai_tools.py`](#appllmopenai_toolspy)
   - [`app/llm/__init__.py`](#appllm__init__py)
3. [Tools & Sandbox Execution Layer (`app/tools/`)](#3-tools--sandbox-execution-layer-apptools)
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
4. [Agent Runtime & Control Layer (`app/agent/`)](#4-agent-runtime--control-layer-appagent)
   - [`app/agent/clock.py`](#appagentclockpy)
   - [`app/agent/budget.py`](#appagentbudgetpy)
   - [`app/agent/cost.py`](#appagentcostpy)
   - [`app/agent/history.py`](#appagenthistorypy)
   - [`app/agent/loop_guard.py`](#appagentloop_guardpy)
   - [`app/agent/state.py`](#appagentstatepy)
   - [`app/agent/trace.py`](#appagenttracepy)
   - [`app/agent/loop.py`](#appagentlooppy)
   - [`app/agent/__init__.py`](#appagent__init__py)
5. [Test Suite Architecture & Quality Assurance (`tests/`)](#5-test-suite-architecture--quality-assurance-tests)
   - [`tests/builders.py`](#testsbuilderspy)
   - [Test Categories Breakdown (151 Tests in 25 Modules)](#test-categories-breakdown-151-tests-in-25-modules)
   - [Automation Quality Tooling](#automation-quality-tooling)

---

## 1. Root & Entry Point Layer

Root layer သည် application components များကို စတင် configure လုပ်ပြီး run ပေးသည့် entry point ဖြစ်သည်။

### `app/main.py`
- **တာဝန်**: End-to-end agent application execution entry point ဖြစ်သည်။ Environment variables ဖတ်ယူခြင်း၊ Tool များ စုစည်းခြင်း၊ LLM client ကို retry policy ဖြင့် wrap လုပ်ခြင်း၊ Tracing sink တပ်ဆင်ခြင်းနှင့် agent loop စတင် မောင်းနှင်ခြင်းတို့ကို တာဝန်ယူသည်။
- **အဓိက အချက်များ**:
  - `workspace = Workspace(Path("."))`: လက်ရှိ directory ကို sandboxed workspace အဖြစ် သတ်မှတ်သည်။
  - `registry = ToolRegistry()`: `ReadFileTool`, `ListFilesTool`, `SearchTextTool` တို့ကို မှတ်ပုံတင်သည်။
  - `ResilientClient(OpenAIClient(...), policy=RetryPolicy())`: Provider SDK client ကို stateless retry decorator ဖြင့် wrap လုပ်သည်။
  - `JsonlFileSink(Path("traces/runs.jsonl"))`: Lifecycle events များကို disk သို့ append-only persist လုပ်ပေးသည်။
  - `AgentLoop`: Per-run guard factories, token budgets, timeout budgets များကို ချိတ်ဆက်ပြီး `loop.run(prompt)` ကို ခေါ်ယူသည်။

### `app/trace_view.py`
- **တာဝန်**: Structured trace logs (`traces/runs.jsonl`) များကို human-readable tabular format ဖြင့် ပြသပေးသော Standalone CLI Viewer ဖြစ်သည်။
- **Decoupled Architecture**: `app.agent` သို့မဟုတ် `app.llm` မှ class များကို တိုက်ရိုက် import မလုပ်ဘဲ raw JSONL line parsing ဖြင့်သာ အလုပ်လုပ်သည်။ ထို့ကြောင့် runtime internals ပြောင်းလဲသွားသော်လည်း အဟောင်း trace logs များကို error မတက်ဘဲ ဖတ်ရှုနိုင်ပါသည်။
- **အဓိက Features**:
  - `--list`: ဖိုင်အတွင်းရှိ run IDs အားလုံးကို list ထုတ်ပြသည်။
  - `latest`: နောက်ဆုံး run ၏ execution metrics ကို ပြသသည်။
  - `<prefix>`: Run ID ၏ ပထမ စာလုံးအနည်းငယ်ဖြင့် disambiguation matching ပြုလုပ်ပေးသည်။
  - **Metrics Aggregation**: Wall-clock time, LLM time (wall share %), Tools time, slowest LLM call, token usage, cost USD များကို တွက်ချက်ပြသပေးသည်။
  - **Incomplete Detection**: Crashed ဖြစ်သွားသော သို့မဟုတ် unfinished run များကို `"incomplete (no run_finished)"` ဟု အတိအကျ ဖော်ပြပေးသည်။

### `conftest.py`
- **တာဝန်**: Pytest root configuration ဖိုင်ဖြစ်ပြီး root directory ကို `sys.path` ထဲသို့ ထည့်သွင်းပေးသဖြင့် test module များမှ `from app.xxx import ...` ဟု သန့်ရှင်းစွာ ခေါ်ယူနိုင်စေသည်။

---

## 2. LLM Subsystem Layer (`app/llm/`)

Provider များနှင့် ချိတ်ဆက်လုပ်ဆောင်သော သီးသန့် subsystem ဖြစ်ပြီး vendor-specific details များကို core agent ထံသို့ မပေါက်ကြားစေရန် provider-independent abstractions များကို တည်ဆောက်ထားသည်။

### `app/llm/types.py`
- **`Usage`**: Input tokens နှင့် output tokens ကို ကိုယ်စားပြုသော immutable dataclass ဖြစ်သည်။ `__add__` operator overloading ပါဝင်ပြီး usage နှစ်ခုကို ပေါင်းစပ်နိုင်သည်။
- **`extract_usage(response)`**: OpenAI/Groq response object မှ tokens များကို provider-independent `Usage` သို့ normalise လုပ်ပေးသည်။ Usage မပါလာပါက `None` ပြန်ပေးသည် (Silent 0 မပေးဘဲ fail-closed budgeting ကို အာမခံသည်)။
- **`AttemptRecord`**: LLM call ကျရှုံးမှု တစ်ကြိမ်ချင်းစီ၏ attempt နံပါတ်, error message, `ErrorKind`, `delay_seconds`, `retry_after_seconds`, `latency_ms` တို့ကို မှတ်တမ်းတင်သော dataclass ဖြစ်သည်။
- **Message Constructors**:
  - `user_message(content)`: `{"role": "user", "content": ...}`
  - `assistant_message(response)`: `{"role": "assistant", "content": ..., "tool_calls": ...}`
  - `tool_result_message(call_id, output)`: `{"role": "tool", "call_id": ..., "output": ...}`

### `app/llm/errors.py`
- **`LLMCallFailed`**: Transient retries အကြိမ်ရေ ကုန်ဆုံးသွားပါက သို့မဟုတ် permanent error ကြုံတွေ့ရပါက ပစ်သော exception ဖြစ်သည်။ `attempt_log: tuple[AttemptRecord, ...]` ပါရှိသည်။
- **`DeadlineExceeded`**: Run wall-clock budget ကုန်ဆုံးခါနီးအချိန်တွင် retry မစောင့်တော့ဘဲ fail-fast ထွက်ခွာသည့် exception ဖြစ်သည်။

### `app/llm/retry.py`
- **`ErrorKind` Enum**: `TRANSIENT` (retry လုပ်နိုင်သော error: 429, 500, 503, connection drop) နှင့် `PERMANENT` (retry မလုပ်သင့်သော error: 400, 401, 404, invalid auth).
- **`RetryPolicy`**:
  - `max_retries` (default: 3), `initial_delay_seconds` (1.0), `backoff_multiplier` (2.0), `max_delay_seconds` (30.0).
  - `decide(attempt, error_kind)`: Exponential backoff delay ကို တွက်ချက်ပြီး `RetryDecision(should_retry, delay_seconds, reason)` ပြန်ပေးသည်။

### `app/llm/llm_errors.py`
- **`classify_llm_error(exc)`**: Exception ၏ status code, class type သို့မဟုတ် error message ကို စစ်ဆေးပြီး `ErrorKind.TRANSIENT` သို့မဟုတ် `PERMANENT` အဖြစ် ခွဲခြားသည်။
- **`retry_after_seconds(exc)`**:
  - `_from_header`: HTTP response ၏ `retry-after` header (HTTP-date သို့မဟုတ် integer seconds) ကို ဖတ်ယူသည်။
  - `_from_message`: Message text တွင် ပါလာသော `"Please try again in 20.085s"` ပုံစံကို safe non-backtracking regex ဖြင့် ရှာဖွေ extract လုပ်သည်။

### `app/llm/client.py`
- **`LLMClient` Protocol**: Client အားလုံး လိုက်နာရမည့် generic interface:
  ```python
  def complete(self, *, messages: list[dict[str, Any]], tools: Sequence[Tool], should_abort: Callable[[], bool] | None = None) -> LLMResponse: ...
  ```

### `app/llm/openai_client.py`
- **`OpenAIClient`**: Official OpenAI SDK (Responses API) ဖြင့် LLM ကို ခေါ်ဆိုသည့် client ဖြစ်သည်။
- **`max_retries=0`**: SDK ၏ built-in opaque retry ကို ပိတ်ထားပြီး application layer (`ResilientClient`) ကသာ backoff နှင့် deadline awareness ကို စီမံသည်။
- **`_to_openai_input`**: Provider-neutral messages ကို OpenAI format သို့ ပြောင်းလဲသည်။
- **`_dump_item`**: Provider response items များကို serializable dict အဖြစ် convert လုပ်ပြီး နောက် conversation turn တွင် format မပျက် replay ပြန်ပို့နိုင်စေသည်။

### `app/llm/fake_client.py`
- **`FakeLLMClient` & `FakeResponse`**: Unit test များတွင် deterministic response များ ထုတ်ပေးနိုင်ရန် provider double ဖြစ်သည်။ Response sequences များကို step-by-step ပေးပို့နိုင်သည်။

### `app/llm/resilient_client.py`
- **`ResilientClient`**: Stateless retry decorator ဖြစ်သည်။
- **Retry-After Hint Override**: Provider က transient error တွင် hint ပေးလာပါက `delay = max(backoff, hint)` ဖြင့် အနည်းဆုံး hint ပမာဏ စောင့်ဆိုင်းသည်။
- **Fail-Fast Cap (`max_retry_after_seconds=60.0`)**: Provider hint သည် 60s ကျော်လွန်ပါက အချိန်မဖြုန်းဘဲ ချက်ချင်း `LLMCallFailed` ပစ်သည်။
- **Per-Attempt Latency Tracking**: ကျရှုံးခဲ့သော attempt တိုင်း၏ `latency_ms` ကို တိုင်းတာမှတ်တမ်းတင်သည်။
- **Deadline Awareness**: `should_abort()` callable က true ဖြစ်နေပါက retry မလုပ်ဘဲ `DeadlineExceeded` ချက်ချင်း ပစ်သည်။

### `app/llm/openai_tools.py`
- **`to_openai_tool(tool)`**: Runtime tool object ကို OpenAI function schema (`{"type": "function", "strict": True, ...}`) သို့ convert လုပ်ပေးသည်။

### `app/llm/__init__.py`
- LLM subsystem ၏ public contracts များကို သန့်ရှင်းစွာ export လုပ်ပေးသည်။

---

## 3. Tools & Sandbox Execution Layer (`app/tools/`)

Tools layer သည် Agent ၏ လက်တွေ့လုပ်ဆောင်နိုင်စွမ်း (actions) ဖြစ်ပြီး Filesystem ကို စစ်ဆေးဖတ်ရှုနိုင်သော tools များ၊ sandbox boundary နှင့် arguments validation များ ပါဝင်ပါသည်။

### `app/tools/base.py`
- **`Tool` (ABC)**: Tool အားလုံး လိုက်နာရမည့် base class ဖြစ်သည်။
- **Single Source of Truth**: Tool တစ်ခုချင်းစီသည် argument model (`args_model`) ကိုသာ ကြေညာရပြီး model-facing JSON schema (`input_schema`) နှင့် runtime validation နှစ်ခုစလုံးကို ထို model မှ အလိုအလျောက် derive ပြုလုပ်သည်။

### `app/tools/call.py` & `app/tools/call_parsing.py`
- **`ToolCall`**: Model က ခေါ်ဆိုလိုက်သော `call_id`, `tool_name`, `arguments`, `parse_error` တို့ကို သိမ်းဆည်းသည့် dataclass ဖြစ်သည်။
- **`parse_tool_call`**: Raw arguments string ကို JSON parse လုပ်သည်။ JSON decode မအောင်မြင်ပါက crash မဖြစ်ဘဲ `parse_error` string အဖြစ် tool call ထဲတွင် သယ်ဆောင်သွားပြီး observation ပြန်ပို့နိုင်စေသည်။

### `app/tools/execution.py`
- **`ToolExecution`**: Tool run ပြီးနောက် ရရှိလာသော `tool_name`, `arguments`, `success`, `result`, `error`, `duration_ms` တို့ကို သိမ်းဆည်းသည့် dataclass ဖြစ်သည်။

### `app/tools/workspace.py`
- **`Workspace`**: Filesystem security sandbox ဖြစ်သည်။
- **`resolve(relative_path)`**: Path traversal attacks (`../`, `../../etc/passwd`) များကို စစ်ဆေးတားဆီးပြီး path သည် workspace root boundary အတွင်း၌သာ တည်ရှိကြောင်း အာမခံသည်။ ကျော်လွန်ပါက `ValueError("escapes workspace")` ပစ်သည်။

### `app/tools/schemas.py` & `app/tools/schema_utils.py`
- **Pydantic Argument Schemas**: `ListFilesArgs`, `ReadFileArgs`, `SearchTextArgs`.
- **`strict_json_schema`**: Pydantic model မှ OpenAI strict tool calling နှင့် ကိုက်ညီသော JSON Schema (`additionalProperties: False`, required fields အားလုံး ပါဝင်မှု) ကို ထုတ်ပေးသည်။

### `app/tools/validation.py`
- **`format_validation_error(exc)`**: Pydantic `ValidationError` မှ လူနှင့် LLM နားလည်လွယ်သော observation error message string အဖြစ် ပြောင်းလဲပေးသည်။

### `app/tools/registry.py` & `app/tools/executor.py`
- **`ToolRegistry`**: Tool များကို နာမည်ဖြင့် register လုပ်ခြင်းနှင့် list ထုတ်ပေးခြင်း။
- **`ToolExecutor`**: Tool မ run မီ Pydantic model ဖြင့် arguments validation မဖြစ်မနေ စစ်ဆေးသည်။ Validation ကျရှုံးပါက execution မလုပ်ဘဲ `ToolExecution(success=False, error=...)` ပြန်ပေးသည်။

### Built-in Sandboxed Tools
- **`ListFilesTool` (`app/tools/list_files.py`)**: Directory အတွင်းရှိ ဖိုင်များနှင့် ဖိုဒါများကို စာရင်းထုတ်ပေးသည်။
- **`ReadFileTool` (`app/tools/read_file.py`)**: ဖိုင်ဖတ်ပေးသည်။ Default 100KB context guard ပါဝင်ပြီး binary/non-UTF8 ဖိုင်များကို ငြင်းပယ်သည်။
- **`SearchTextTool` (`app/tools/search_text.py`)**: Workspace ဖိုင်များအတွင်း substring ရှာပေးသည်။ Dependency/cache directories (`.git`, `.venv`, `node_modules`) များကို `os.walk` prune ဖြင့် skip လုပ်သဖြင့် အလွန်မြန်ဆန်သည်။

---

## 4. Agent Runtime & Control Layer (`app/agent/`)

Agent ၏ ဦးနှောက်နှင့် ထိန်းချုပ်ရေးဗဟို (Core Engine) ဖြစ်ပါသည်။ Loop, State, Guards, Budgets နှင့် Tracing အားလုံး ပါဝင်သည်။

### `app/agent/clock.py`
- **`Clock` Protocol & `MonotonicClock`**: Deterministic unit testing အတွက် အချိန် interface ဖြစ်သည်။ Tests များတွင် `FakeClock` ဖြင့် အစားထိုးနိုင်သည်။

### `app/agent/budget.py`
- **`RuntimeBudget`**: `max_wall_time_seconds` (default: 60.0s) နှင့် `per_call_timeout_seconds` (30.0s).
- **`BudgetTracker`**: လက်ကျန်အချိန်နှင့် deadline ကုန်ဆုံးမှု (`is_expired()`) ကို စစ်ဆေးပေးသည်။

### `app/agent/cost.py`
- **`ModelPricing`**: Input tokens နှင့် output tokens ၏ USD နှုန်းထား။
- **`TokenBudget`**: `max_input_tokens`, `max_output_tokens`, `max_total_tokens`, `max_cost_usd`.
- **`UsageTracker`**: Run တစ်ခုအတွင်း token သုံးစွဲမှုနှင့် စုစုပေါင်း ကုန်ကျစရိတ်ကို မှတ်တမ်းတင်ပြီး budget ကျော်လွန်ပါက အကြောင်းရင်း ပြန်ပေးသည်။

### `app/agent/history.py`
- **`ExecutionRecord` & `ExecutionHistory`**: Tool execution တစ်ခုချင်းစီ၏ audit trail ကို မှတ်တမ်းတင်ပြီး JSON serialization ပြုလုပ်ပေးသည်။

### `app/agent/loop_guard.py`
- **`call_fingerprint(tool_name, arguments)`**: Canonical JSON serialization ဖြင့် argument order မတူသော်လည်း stable fingerprint ထုတ်ပေးသည်။
- **`LoopGuard`**: `block_on_nth_call = 3` ဖြင့် တူညီသော tool call ကို တတိယအကြိမ်မြောက်တွင် execution မလုပ်မီ ကြိုတင်တားဆီးသည်။
- **`ConsecutiveCounter`**: Malformed tool arguments များကို စောင့်ကြည့်ပြီး limit (default: 3) အကြိမ် ဆက်တိုက် fail ဖြစ်ပါက `LOOP_DETECTED` ဖြင့် ရပ်တန့်သည်။ Valid tool call ရောက်ပါက reset ဖြစ်သည်။

### `app/agent/state.py`
- **`AgentStatus` Enum**: `RUNNING`, `COMPLETED`, `MAX_ITERATIONS`, `TIMEOUT`, `LOOP_DETECTED`, `TOKEN_BUDGET_EXCEEDED`, `LLM_FAILED`.
- **`AgentState`**: Conversation history, iteration count, status, final response, history, usage, `llm_attempts` နှင့် `run_id` (Trace correlation UUID) တို့ ပါဝင်သည်။

### `app/agent/trace.py`
- **`TraceEvent`**: Immutable (`frozen=True`) trace record: `run_id`, monotonic `seq`, ISO UTC `ts`, `type`, `data`.
- **`InMemorySink`**: List ဖြင့် event များကို သိမ်းဆည်းပြီး tests များတွင် စစ်ဆေးသည်။
- **`JsonlFileSink`**: Append-only JSON Lines file သို့ ချက်ချင်း flush ရေးသားသည်။
- **`TraceRecorder`**: Run emitter ဖြစ်သည်။ Sink ချွတ်ယွင်းမှုသည် agent run ကို မထိခိုက်စေရန် fail-safe exception handling ပါဝင်သည်။

### `app/agent/loop.py`
- **`AgentLoop`**: Core Orchestration Engine ဖြစ်သည်။
- **Low Cognitive Complexity Architecture (Refactored to 6)**:
  - `run()` method ကို clean helper functions များအဖြစ် ခွဲထုတ်ထားသည်:
    - `_run_iteration`: Iteration တစ်ခုချင်းစီ၏ lifecycle pipeline ကို စီမံသည်။
    - `_check_iteration_budget`: Timeout နှင့် max iterations စစ်ဆေးသည်။
    - `_call_llm`: LLM client ခေါ်ဆိုခြင်း၊ retry attempts မှတ်တမ်းတင်ခြင်းနှင့် trace emit ပြုလုပ်ခြင်း။
    - `_handle_final_response`: Empty answer မဟုတ်ပါက `COMPLETED` သတ်မှတ်သည်။
    - `_process_tool_calls`: Parse failures, LoopGuard စစ်ဆေးခြင်း၊ tool execution နှင့် observations ပို့ဆောင်ခြင်း။
    - `_attempts_payload`: LLM attempts metadata များကို trace payload အဖြစ် serialise လုပ်သည်။

---

## 5. Test Suite Architecture & Quality Assurance (`tests/`)

Agent Runtime သည် **151 test cases across 25 modules** ဖြင့် 100% deterministic test coverage ကို ပေးစွမ်းထားပြီး network call သို့မဟုတ် `time.sleep()` လုံးဝမသုံးဘဲ ~1.0 second အတွင်း အပြည့်အစုံ run နိုင်ပါသည်။

### `tests/builders.py`
- **`FakeClock`**: Manual time advancement ဖြင့် timeout များကို စက္ကန့်ပိုင်းအတွင်း စမ်းသပ်သည်။
- **`FakeSDK`**: `OpenAIClient` ၏ SDK interaction ကို intercept စစ်ဆေးသည်။
- **`ScriptedClient`**: Scripted sequence (`RateLimitError`, `FakeResponse`) များကို sequential အတိုင်း ထုတ်ပေးသည်။
- **`function_call_item` & `tool_outputs`**: Test payload များကို တသမတ်တည်း ထုတ်ပေးသော builders များ ဖြစ်သည်။

### Test Categories Breakdown
1. **Architecture & Layering Rules (`test_layering.py`)**: AST traversal ဖြင့် layer boundaries (agent -> llm -> tools) ကို enforce လုပ်သည်။
2. **Loop Orchestration & State (`test_agent_loop.py`, `test_a2_loop.py`, `test_agent_state.py`, `test_per_run_state.py`)**: Happy path, termination, state isolation စစ်ဆေးသည်။
3. **Runtime Guards & Budgets (`test_runtime_guards.py`, `test_loop_guard.py`, `test_budget.py`, `test_usage_budget.py`)**: Loop repetition, timeout, token/cost budgets စစ်ဆေးသည်။
4. **Resiliency, Retry & Network Faults (`test_retry.py`, `test_retry_after.py`, `test_integration_pass.py`)**: Exponential backoff, `Retry-After` header/message parsing, `max_retry_after_seconds=60.0` fail-fast, deadline aborts စစ်ဆေးသည်။
5. **Fault Injection & Malformed Call Recovery (`test_fault_injection.py`, `test_error_recovery.py`)**: Malformed arguments, non-object arguments, consecutive malformed cap စစ်ဆေးသည်။
6. **Tool Schemas & Sandboxed Workspace (`test_tools.py`, `test_file_tools.py`, `test_workspace.py`, `test_tools_schemas.py`, `test_schema_derivation.py`, `test_validation_errors.py`)**: Strict schema, path traversal rejection, file limits စစ်ဆေးသည်။
7. **Provider Integration & Tools Conversion (`test_openai_client.py`, `test_openai_tools.py`, `test_a2_foundations.py`)**: Provider SDK contracts, tool conversion, opaque replay စစ်ဆေးသည်။
8. **Structured Trace Logging & CLI Viewer (`test_trace.py`, `test_trace_view.py`)**: Event schemas, file sinks, fail-safe behavior, CLI viewer filtering, incomplete run handling စစ်ဆေးသည်။

### Automation Quality Tooling
```bash
# Production Test Suite (151 tests)
.venv/Scripts/pytest -q

# Strict Linter & Hygiene Check
.venv/Scripts/ruff check .

# Static Type Analysis (36 source files)
.venv/Scripts/mypy app
```
