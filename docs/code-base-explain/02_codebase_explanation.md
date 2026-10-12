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
   - [`app/llm/reasoning.py`](#appllmreasoningpy)
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
   - [`app/agent/prompts.py`](#appagentpromptspy)
   - [`app/agent/plan.py`](#appagentplanpy)
   - [`app/agent/plan_parsing.py`](#appagentplan_parsingpy)
   - [`app/agent/planner.py`](#appagentplannerpy)
   - [`app/agent/ledger.py`](#appagentledgerpy)
   - [`app/agent/nudges.py`](#appagentnudgespy)
   - [`app/agent/clock.py`](#appagentclockpy)
   - [`app/agent/budget.py`](#appagentbudgetpy)
   - [`app/agent/cost.py`](#appagentcostpy)
   - [`app/agent/history.py`](#appagenthistorypy)
   - [`app/agent/loop_guard.py`](#appagentloop_guardpy)
   - [`app/agent/state.py`](#appagentstatepy)
   - [`app/agent/trace.py`](#appagenttracepy)
   - [`app/agent/loop.py`](#appagentlooppy)
   - [`app/agent/__init__.py`](#appagent__init__py)
5. [Automated Evaluation Subsystem (`evals/`)](#5-automated-evaluation-subsystem-evals)
   - [`evals/spec.py`](#evalsspecpy)
   - [`evals/graders.py`](#evalsgraderspy)
   - [`evals/runner.py`](#evalsrunnerpy)
   - [`evals/compare.py`](#evalscomparepy)
   - [`evals/run.py`](#evalsrunpy)
   - Synthetic Shop Fixture & Tasks (`evals/tasks.yaml`)
6. [Test Suite Architecture & Quality Assurance (`tests/`)](#6-test-suite-architecture--quality-assurance-tests)

---

## 1. Root & Entry Point Layer

Root layer သည် application components များကို စတင် configure လုပ်ပြီး run ပေးသည့် composition root ဖြစ်သည်။

### `app/main.py`
- **တာဝန်**: End-to-end agent application execution entry point ဖြစ်သည်။
- **အဓိက အစိတ်အပိုင်းများ**:
  - `workspace = Workspace(Path.cwd())`: လက်ရှိ working directory ကို sandboxed workspace အဖြစ် သတ်မှတ်သည်။
  - `registry = ToolRegistry()`: `ReadFileTool`, `ListFilesTool`, `SearchTextTool` တို့ကို မှတ်ပုံတင်သည်။
  - `VerboseToolExecutor`: `ToolExecutor` ကို wrap လုပ်ထားပြီး tool တစ်ခုချင်းစီ၏ observation result (ဥပမာ `21 item(s)` သို့မဟုတ် `20107 bytes read`) ကို live console preview ပြပေးသည်။
  - `ResilientClient(OpenAIClient(...), policy=RetryPolicy(), sleep=sleep_with_progress)`: Provider SDK client ကို stateless retry decorator ဖြင့် wrap လုပ်ပြီး 429 rate limit ကြုံပါက စောင့်ဆိုင်းချိန်ကို live progress ပြပေးသည်။
  - `ConsoleAndFileSink`: `JsonlFileSink(Path("traces/runs.jsonl"))` သို့ disk append-only flush လုပ်ပေးသလို Terminal console ပေါ်တွင် turn-by-turn live visualizer အဖြစ် print ပြုလုပ်ပေးသည်။
  - `AgentLoop.run(prompt)`: Agent cycle ကို စတင်မောင်းနှင်သည်။

### `app/trace_view.py`
- **တာဝန်**: Structured trace logs (`traces/runs.jsonl`) များကို human-readable tabular format ဖြင့် ပြသပေးသော Standalone CLI Viewer ဖြစ်သည်။
- **Decoupled Architecture**: `app.agent` သို့မဟုတ် `app.llm` မှ class များကို တိုက်ရိုက် import မလုပ်ဘဲ raw JSONL line parsing ဖြင့်သာ အလုပ်လုပ်သည်။ ထို့ကြောင့် runtime internals ပြောင်းလဲသွားသော်လည်း အဟောင်း trace logs များကို error မတက်ဘဲ ဖတ်ရှုနိုင်ပါသည်။
- **အဓိက Commands**:
  - `python -m app.trace_view --list`: Run IDs စာရင်းထုတ်ပြသည်။
  - `python -m app.trace_view latest`: နောက်ဆုံး run ၏ execution metrics ကို ပြသသည်။
  - `python -m app.trace_view <run_id|prefix>`: သတ်မှတ်ထားသော Run ID ကို ကြည့်ရှုသည်။

### `conftest.py`
- **တာဝန်**: Pytest root configuration ဖိုင်ဖြစ်ပြီး root directory ကို `sys.path` ထဲသို့ ထည့်သွင်းပေးသဖြင့် test module များမှ `from app.xxx import ...` ဟု သန့်ရှင်းစွာ ခေါ်ယူနိုင်စေသည်။

---

## 2. LLM Subsystem Layer (`app/llm/`)

Provider များနှင့် ချိတ်ဆက်လုပ်ဆောင်သော သီးသန့် subsystem ဖြစ်ပြီး vendor-specific details များကို core agent ထံသို့ မပေါက်ကြားစေရန် provider-independent abstractions များကို တည်ဆောက်ထားသည်။

### `app/llm/types.py`
- **`Usage`**: Input tokens နှင့် output tokens ကို ကိုယ်စားပြုသော immutable dataclass ဖြစ်သည်။ `__add__` operator overloading ပါဝင်ပြီး usage နှစ်ခုကို ပေါင်းစပ်နိုင်သည်။
- **`extract_usage(response)`**: Provider response object မှ tokens များကို provider-independent `Usage` သို့ normalise လုပ်ပေးသည်။ Usage မပါလာပါက `None` ပြန်ပေးသည် (Fail-closed budgeting)။
- **`AttemptRecord`**: LLM call ကျရှုံးမှု တစ်ကြိမ်ချင်းစီ၏ attempt နံပါတ်, error message, `ErrorKind`, `delay_seconds`, `retry_after_seconds`, `latency_ms` တို့ကို မှတ်တမ်းတင်သော dataclass ဖြစ်သည်။
- **`LLMResponse`**: Provider neutral response: `text: str`, `tool_calls: tuple[ToolCall, ...]`, `usage: Usage | None`, `attempts: tuple[AttemptRecord, ...]`, `assistant_items: list[Any]`, `reasoning: str = ""`.
- **Message Constructors**: `user_message`, `assistant_message`, `tool_result_message`.

### `app/llm/reasoning.py`
- **`extract_reasoning(items)`**: Provider ၏ response item များ (ဥပမာ Groq Responses API ၏ `type: "reasoning"` block) ထဲမှ native Chain-of-Thought reasoning text ကို ဆွဲထုတ်ပေးသော တစ်ခုတည်းသော module ဖြစ်သည်။

### `app/llm/errors.py`
- **`LLMCallFailed`**: Transient retries အကြိမ်ရေ ကုန်ဆုံးသွားပါက သို့မဟုတ် permanent error ကြုံတွေ့ရပါက ပစ်သော exception ဖြစ်သည်။ `attempt_log` ပါရှိသည်။
- **`DeadlineExceeded`**: Run wall-clock budget ကုန်ဆုံးခါနီးအချိန်တွင် retry မစောင့်တော့ဘဲ fail-fast ထွက်ခွာသည့် exception ဖြစ်သည်။

### `app/llm/retry.py` & `app/llm/llm_errors.py`
- **`ErrorKind` Enum**: `TRANSIENT` (429, 500, 503, connection error) သို့မဟုတ် `PERMANENT` (400, 401, 404).
- **`RetryPolicy`**: `max_attempts`, `base_delay_seconds`, `max_delay_seconds` ဖြင့် exponential backoff ဆုံးဖြတ်သည်။
- **`retry_after_seconds(exc)`**: HTTP `Retry-After` header သို့မဟုတ် Groq error message (`"Please try again in 20.085s"`) မှ regex ဖြင့် စက္ကန့်ပမာဏကို ရှာဖွေဖော်ထုတ်သည်။

### `app/llm/openai_client.py` & `app/llm/resilient_client.py`
- **`OpenAIClient`**: OpenAI SDK ဖြင့် complete() ခေါ်ယူသည်။ `output_schema` ပါလာပါက `text.format` JSON schema strict mode အသုံးပြုသည်။
- **`ResilientClient`**: Stateless retry decorator ဖြစ်ပြီး Provider retry hint နှင့် backoff delay အနက် ကြီးရာကို ရွေးချယ်သည်။ `max_retry_after_seconds=60.0` ကျော်ပါက fail-fast လုပ်သည်။
- **`FakeLLMClient` & `FakeResponse` (`app/llm/fake_client.py`)**: Unit test များအတွက် network မလိုဘဲ responses များကို deterministically ပြန်ပေးသော test doubles များ ဖြစ်သည်။

---

## 3. Tools & Sandbox Execution Layer (`app/tools/`)

### `app/tools/base.py`
- **`Tool` Abstract Base Class**:
  - `name: str`, `description: str`, `args_model: type[BaseModel]` (Abstract single source of truth).
  - `input_schema`: `strict_json_schema(args_model)` မှ အလိုအလျောက် derive လုပ်သည်။
  - `run(args: dict[str, Any]) -> Any`: Concrete execution.

### `app/tools/workspace.py`
- **`Workspace`**: Filesystem security sandbox ဖြစ်သည်။
- **`resolve(relative_path)`**: Path traversal attacks (`../`, `../../etc/passwd`) များကို စစ်ဆေးတားဆီးပြီး path သည် workspace root boundary အတွင်း၌သာ တည်ရှိကြောင်း အာမခံသည်။

### `app/tools/schemas.py` & `app/tools/schema_utils.py`
- Pydantic models: `ListFilesArgs`, `ReadFileArgs`, `SearchTextArgs`.
- `strict_json_schema`: OpenAI strict tool calling format (`additionalProperties: false`, required fields) ကို ထုတ်ပေးသည်။

### Built-in Sandboxed Tools
- **`ListFilesTool` (`app/tools/list_files.py`)**: Directory အတွင်းရှိ ဖိုင်များနှင့် ဖိုဒါများကို စာရင်းထုတ်ပေးသည်။
- **`ReadFileTool` (`app/tools/read_file.py`)**: ဖိုင်ဖတ်ပေးသည်။ Default 100KB context guard ပါဝင်သည်။
- **`SearchTextTool` (`app/tools/search_text.py`)**: Workspace ဖိုင်များအတွင်း substring ရှာပေးသည်။ Dependency/cache directories (`.git`, `.venv`, `node_modules`) များကို skip လုပ်သည်။

---

## 4. Agent Runtime & Control Layer (`app/agent/`)

Agent ၏ ဦးနှောက်နှင့် ထိန်းချုပ်ရေးဗဟို (Core Engine) ဖြစ်ပါသည်။

### `app/agent/prompts.py`
- **`Prompt` Dataclass**: `name`, `text`, `sha` (content hash ရှစ်လုံး), `label`.
- **`BASELINE`**: v0.2 Baseline prompt (`baseline@dd04b6a4`).
- **`GROUNDED_V1`**: Baseline + Grounding rule (`"Inspect code before answering"`, `grounded-v1@284f3dcd`).
- **`PLANNER_V1`**: Upfront planning prompt.

### `app/agent/plan.py` & `app/agent/planner.py`
- **`Plan` & `PlanStep`**: Ordered execution steps; `ids` နှင့် `status` (`PENDING`, `DONE`, `FAILED`) များကို ကုဒ်က တာဝန်ယူ စီမံသည်။
- **`Planner`**: Tool မပါသော သီးသန့် schema-constrained LLM call ဖြင့် `PlanSpec{steps: list[str]}` ကို ဖန်တီးပေးသည်။ Plan မအောင်မြင်ပါက fallback အဖြစ် no-plan ဖြင့် loop ကို ဆက်လက် run စေသည်။

### `app/agent/ledger.py`
- **`build_ledger(records)`**: Model ၏ ပြောကြားချက်များ မပါဝင်ဘဲ `ExecutionRecord` သမိုင်းကြောင်းမှ တိုက်ရိုက် derive လုပ်ထားသော objective code-derived summary (ဖတ်ခဲ့သော ဖိုင်များ၊ ရှာခဲ့သော queries + match counts၊ failed calls) ကို ထုတ်ပေးသည်။ AgentLoop တွင် N turns တိုင်း system note အဖြစ် ထည့်သွင်းပေးသည်။

### `app/agent/nudges.py`
- **`trailing_failures` & `failure_nudge`**: Tool calls များ ဆက်တိုက် fail ဖြစ်ပါက စစ်ဆေးရန် သတိပေးသည့် note.
- **`EMPTY_ANSWER_NUDGE`**: Model က tool လည်းမခေါ်၊ အဖြေလည်း မပါဘဲ whitespace ပေးပါက ပြန်လည်သတိပေးသည့် note.
- **`trailing_empty_searches` & `no_progress_nudge`**: Search text result match 0 ခု streak $\ge 2$ ဖြစ်ပါက *"မရှိပါက အတင်းမရှာဘဲ final answer တွင် ရှင်းလင်းစွာ ဝန်ခံပါ"* ဟူသော advisory give-up note ကို ထည့်သွင်းပေးသည်။

### `app/agent/loop_guard.py`
- **`call_fingerprint`**: Canonical JSON serialization ဖြင့် stable fingerprint ထုတ်ပေးသည်။
- **`LoopGuard`**: `block_on_nth_call = 3` ဖြင့် တူညီသော tool call ကို တတိယအကြိမ်တွင် block လုပ်သည်။
- **`ConsecutiveCounter`**: Malformed tool arguments ဆက်တိုက် fail ဖြစ်မှုကို ကန့်သတ်သည်။

### `app/agent/state.py`
- **`AgentStatus` Enum**: `RUNNING`, `COMPLETED`, `MAX_ITERATIONS`, `TIMEOUT`, `LOOP_DETECTED`, `TOKEN_BUDGET_EXCEEDED`, `LLM_FAILED`.
- **`Thought`**: Iteration နှင့် reasoning text ကို သိမ်းဆည်းသည်။
- **`AgentState`**: Conversation, iteration, status, final_response, usage, llm_attempts, run_id, thoughts, plan, `last_nudged_empty`, `last_nudged_failures`, `empty_answer_retries`.

### `app/agent/loop.py`
- **`AgentLoop`**: Core Orchestration Engine ဖြစ်သည်။
- **Clean Sub-methods Architecture**:
  - `_make_plan`: Loop မစတင်မီ planner ခေါ်ယူခြင်းနှင့် plan ထည့်သွင်းခြင်း။
  - `_run_iteration`: Iteration တစ်ခုချင်းစီ၏ sequential guard checks များကို run သည်။
  - `_record_thought`: LLM response မှ reasoning ကို `state.thoughts` ထဲ ထည့်သည်။
  - `_maybe_add_ledger`: Cadence အလိုက် evidence ledger note ထည့်သွင်းသည်။
  - `_maybe_add_failure_nudge`: Tool failure streak ပြည့်ပါက failure nudge ထည့်သွင်းသည်။
  - `_maybe_add_no_progress_nudge`: Empty search streak ပြည့်ပါက no-progress nudge ထည့်သွင်းသည်။
  - `_handle_final_response`: Empty answer ဖြစ်ပါက retry 1 ကြိမ် ခွင့်ပြုသည်။

---

## 5. Automated Evaluation Subsystem (`evals/`)

Agent Runtime ၏ စွမ်းဆောင်ရည်ကို သိပ္ပံနည်းကျ တိုင်းတာရန် တည်ဆောက်ထားသော Eval Suite ဖြစ်သည်။

### `evals/spec.py`
- **`TaskFile` & `Task`**: Task spec (`name`, `category`, `prompt`, `expect: Expect`).
- **`Expect`**: `kind` (`refusal`, `answer_contains`, `answer_equals`), `values`, `must_read`, `forbidden`.

### `evals/graders.py`
- **`RunResult`**: Run ၏ status, answer, `read_paths`, fixture_dir, workspace_dir.
- **`grade(task, result)`**: Programmatic deterministic checks:
  - `contains_word`: Word-boundary regex ဖြင့် target words ပါမပါ စစ်ဆေးသည်။
  - `must_read`: Agent သည် သက်ဆိုင်ရာ code file ကို read_file ခေါ်ခဲ့သလား စစ်ဆေးသည်။
  - `forbidden`: Decoy ဖိုင်များ သို့မဟုတ် မပါဝင်ရမည့် စကားလုံးများ မပါဝင်ကြောင်း စစ်ဆေးသည်။
  - `refusal_indicated`: Absence task များအတွက် AST allowlist ဖြင့် real repo files များကို စစ်ပြီး pointer-verb detection ဖြင့် refusal အစစ်အမှန် ဟုတ်မဟုတ် စစ်ဆေးသည် (`EVAL_VERSION=4`)။

### `evals/runner.py` & `evals/compare.py`
- **`run_task_once`**: Task တိုင်းအတွက် `evals/fixtures/shop` ကို temporary workspace ထဲ ကူးယူပြီး isolated run ပြုလုပ်သည်။
- **`run_suite`**: Repeats $N$ ကြိမ် run ပြီး token-based cooldown ဖြင့် rate limit မဖြစ်အောင် pacing ထိန်းသည်။
- **`compare(old_report, new_report)`**: Baseline နှစ်ခုကြား pass rate, token cost, latency ကွာခြားချက်ကို diff ပြပေးသည်။

### `evals/run.py`
CLI Entry point:
```bash
# Baseline suite ကို 3 ကြိမ် repeats ဖြင့် run ရန်
python -m evals.run --version v0.7-pos-noprog2 --repeats 3 --no-progress 2

# Report နှစ်ခု ယှဉ်ကြည့်ရန်
python -m evals.run --compare evals/reports/v0.2b.json evals/reports/v0.6-noprog2-neg.json
```

---

## 6. Test Suite Architecture & Quality Assurance (`tests/`)

Agent Runtime သည် **281 tests (278 passed, 3 xfailed)** ဖြင့် deterministic test coverage အပြည့်အဝ ပေးစွမ်းထားပြီး ~1.9s အတွင်း run နိုင်ပါသည်။

```bash
# Automated Test Suite (281 tests)
.venv/Scripts/pytest -q

# Strict Linter Check
.venv/Scripts/ruff check .

# Static Type Analysis (49 source files)
.venv/Scripts/mypy app evals
```
