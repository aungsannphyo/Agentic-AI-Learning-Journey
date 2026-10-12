# Agent Runtime — Codebase Snapshots Gateway (`code-base-snapshot/`)

ဤစာတမ်းသည် Agent Runtime ပရောဂျက်တစ်ခုလုံး၏ Source Code များကို Subsystem အလိုက် သီးခြားစီ အပြည့်အစုံ ကူးယူစုစည်းထားသော **Codebase Snapshots Gateway** ဖြစ်ပါသည်။

LLM (Large Language Model) များထံ Context Window အဖြစ် ထည့်သွင်းပေးလိုသည့်အခါ ဖိုင်အားလုံးကို တစ်ပြိုင်နက် မထည့်ဘဲ လိုအပ်သော Subsystem Snapshot ဖိုင်ကိုသာ ရွေးချယ် ထည့်သွင်းခြင်းဖြင့် Context Window ချွေတာနိုင်ပြီး တိကျသော အဖြေများကို ရရှိစေပါသည်။

---

## ၁။ Snapshots မာတိကာ (Snapshot Index)

| File Link | Subsystem | ပါဝင်သော File အရေအတွက် | အဓိက ပါဝင်သည့် အစိတ်အပိုင်းများ | အကြံပြုထားသော အသုံးပြုမှု |
|:---|:---|:---:|:---|:---|
| [`01_root.md`](file:///c:/Users/uaung/aung_sann_phyo/person/agentic-ai-learning/agent-runtime/docs/code-base-explain/code-base-snapshot/01_root.md) | Root & Entry Layer | 3 files | `app/main.py`, `app/trace_view.py`, `conftest.py` | Entrypoint wiring, CLI trace viewer, runtime execution bootstrap |
| [`02_llm.md`](file:///c:/Users/uaung/aung_sann_phyo/person/agentic-ai-learning/agent-runtime/docs/code-base-explain/code-base-snapshot/02_llm.md) | LLM Subsystem | 11 files | Client protocols, OpenAI/Groq adapter, ResilientClient, Native Reasoning parser, retry backoff | LLM client integration, transient 429 backoff, CoT reasoning capture |
| [`03_tools.md`](file:///c:/Users/uaung/aung_sann_phyo/person/agentic-ai-learning/agent-runtime/docs/code-base-explain/code-base-snapshot/03_tools.md) | Tools & Sandbox Layer | 14 files | `Tool` ABC, Pydantic args schemas, Workspace sandbox, `read_file`, `list_files`, `search_text` | Tool registry, file system sandboxing, JSON schema auto-derivation |
| [`04_agent.md`](file:///c:/Users/uaung/aung_sann_phyo/person/agentic-ai-learning/agent-runtime/docs/code-base-explain/code-base-snapshot/04_agent.md) | Agent Runtime Core | 15 files | `AgentLoop`, `Planner`, `EvidenceLedger`, `LoopGuard`, reactive nudges, budgets, state, tracing | Cognitive loop, guard pipeline, plan generation, nudge injection, trace events |
| [`05_tests_fixtures.md`](file:///c:/Users/uaung/aung_sann_phyo/person/agentic-ai-learning/agent-runtime/docs/code-base-explain/code-base-snapshot/05_tests_fixtures.md) | Test Fixtures & Doubles | 1 file | `tests/builders.py` (`FakeResponse`, `ScriptedClient`, `tool_outputs`, `SdkItem`) | Unit testing without network/sleep, deterministic test authoring |
| [`06_evals.md`](file:///c:/Users/uaung/aung_sann_phyo/person/agentic-ai-learning/agent-runtime/docs/code-base-explain/code-base-snapshot/06_evals.md) | Evaluation Subsystem | 6 files | `evals/__init__.py`, `spec.py`, `graders.py`, `runner.py`, `compare.py`, `run.py` | Benchmark suites, programmatic graders, refusal validation, A/B diff |

---

## ၂။ Subsystem အလိုက် အသေးစိတ် ဖိုင်များ စာရင်း

### (က) Root Layer (`code-base-snapshot/01_root.md`)
- `app/main.py`: Interactive runtime orchestrator with live console event stream (`ConsoleAndFileSink`, `VerboseToolExecutor`).
- `app/trace_view.py`: Terminal-based rich trace visualizer for `traces/runs.jsonl`.
- `conftest.py`: Root pytest configuration adding project directory to `sys.path`.

### (ခ) LLM Layer (`code-base-snapshot/02_llm.md`)
- `app/llm/__init__.py`: Package exports (`LLMClient`, `OpenAIClient`, `ResilientClient`, `FakeLLMClient`, etc.).
- `app/llm/client.py`: `LLMClient` structural protocol (`complete` method signature).
- `app/llm/errors.py`: Runtime LLM exceptions (`LLMCallFailed`, `DeadlineExceeded`).
- `app/llm/fake_client.py`: `FakeLLMClient` & `FakeResponse` deterministic test doubles.
- `app/llm/llm_errors.py`: HTTP status classification (`classify_llm_error`) & `retry_after_seconds` header/message parsing.
- `app/llm/openai_client.py`: Native OpenAI SDK adapter with tool schemas and structured outputs.
- `app/llm/openai_tools.py`: Tool definition converter (`to_openai_tool`) translating Pydantic schemas to OpenAI tool specs.
- `app/llm/reasoning.py`: Provider-agnostic reasoning extractor (`extract_reasoning`) capturing native CoT reasoning content.
- `app/llm/resilient_client.py`: Exponential backoff decorator with `Retry-After` adherence and fail-fast deadline enforcement.
- `app/llm/retry.py`: Stateless retry backoff calculator (`ErrorKind`, `RetryPolicy`, `RetryDecision`).
- `app/llm/types.py`: `LLMResponse`, `Usage`, `extract_usage`, `AttemptRecord`, and message constructors (`user_message`, `assistant_message`, `tool_result_message`).

### (ဂ) Tools Layer (`code-base-snapshot/03_tools.md`)
- `app/tools/__init__.py`: Tool registry exports.
- `app/tools/base.py`: `Tool` abstract base class with single-source-of-truth `args_model`.
- `app/tools/call.py`: `ToolCall` encapsulation.
- `app/tools/call_parsing.py`: Safe JSON call parsing.
- `app/tools/execution.py`: `ToolExecution` execution record.
- `app/tools/executor.py`: Safe executor with validation error interception.
- `app/tools/list_files.py`: Path-traversal safe recursive file listing.
- `app/tools/read_file.py`: Size-bounded, encoding-safe file reader.
- `app/tools/registry.py`: In-memory tool registry with name uniqueness checks.
- `app/tools/schema_utils.py`: Recursive strict JSON Schema sanitizer (`additionalProperties: false`).
- `app/tools/schemas.py`: Tool argument schema generation.
- `app/tools/search_text.py`: Substring and regex text search with line numbers.
- `app/tools/validation.py`: Pydantic input validator returning clean error strings.
- `app/tools/workspace.py`: Canonical path resolution sandbox preventing directory escapes.

### (ဃ) Agent Layer (`code-base-snapshot/04_agent.md`)
- `app/agent/__init__.py`: Agent module exports.
- `app/agent/budget.py`: `TimeBudget` for wall-clock enforcement.
- `app/agent/clock.py`: `Clock` protocol & `MonotonicClock` implementation.
- `app/agent/cost.py`: `TokenBudget` tracking input, output, and total usage.
- `app/agent/history.py`: Agent conversational message sequence management.
- `app/agent/ledger.py`: `EvidenceLedger` tracking files examined and verified facts.
- `app/agent/loop.py`: Core `AgentLoop` driving reasoning, tool dispatch, guards, and nudges.
- `app/agent/loop_guard.py`: `LoopGuard` tracking duplicate consecutive calls and repeated errors.
- `app/agent/nudges.py`: Reactive corrective nudges (`NudgePolicy`, `GiveUpPolicy`).
- `app/agent/plan.py`: `PlanSpec` and `PlanStep` structured planning models.
- `app/agent/plan_parsing.py`: JSON plan parser extracting structured step lists.
- `app/agent/planner.py`: Upfront LLM planner generating actionable execution plans.
- `app/agent/prompts.py`: Dynamic system prompts with tool definitions and runtime rules.
- `app/agent/state.py`: `AgentState` capturing completed steps, status, token costs, and elapsed time.
- `app/agent/trace.py`: Structured JSONL lifecycle event logging (`JsonlFileSink`, `TraceEvent`).

### (င) Evaluation Layer (`code-base-snapshot/06_evals.md`)
- `evals/__init__.py`: Package exports and evaluation subsystem namespace marker.
- `evals/spec.py`: Declarative evaluation task specification (`TaskSpec`, `GradingConfig`).
- `evals/graders.py`: Deterministic programmatic graders (exact, contains, regex, refusal).
- `evals/runner.py`: Isolated evaluation runner with temp workspace duplication and cooldown.
- `evals/compare.py`: Differential comparator for baseline vs candidate benchmark runs.
- `evals/run.py`: CLI driver for batch evaluation execution.

---

## ၃။ အသုံးပြုပုံ လမ်းညွှန် (Usage Guide)

1. **Agent Loop Logic & Guards များကို Debugging ပြုလုပ်လိုလျှင်**:
   - [`code-base-snapshot/04_agent.md`](file:///c:/Users/uaung/aung_sann_phyo/person/agentic-ai-learning/agent-runtime/docs/code-base-explain/code-base-snapshot/04_agent.md) ကိုသာ Context အဖြစ် ထည့်သွင်းပါ။
2. **LLM Calls, Rate Limits (429) နှင့် Native Reasoning များကို မွမ်းမံလိုလျှင်**:
   - [`code-base-snapshot/02_llm.md`](file:///c:/Users/uaung/aung_sann_phyo/person/agentic-ai-learning/agent-runtime/docs/code-base-explain/code-base-snapshot/02_llm.md) ကို အသုံးပြုပါ။
3. **Tools အသစ် ထည့်သွင်းခြင်း သို့မဟုတ် Sandbox Security စစ်ဆေးလိုလျှင်**:
   - [`code-base-snapshot/03_tools.md`](file:///c:/Users/uaung/aung_sann_phyo/person/agentic-ai-learning/agent-runtime/docs/code-base-explain/code-base-snapshot/03_tools.md) ကို အသုံးပြုပါ။
4. **Automated Evaluation Tasks နှင့် Graders အသစ်များ ရေးသားလိုလျှင်**:
   - [`code-base-snapshot/06_evals.md`](file:///c:/Users/uaung/aung_sann_phyo/person/agentic-ai-learning/agent-runtime/docs/code-base-explain/code-base-snapshot/06_evals.md) ကို အသုံးပြုပါ။
