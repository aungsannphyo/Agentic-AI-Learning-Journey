# PROGRESS

## Current: Week 3 / Day 1 DONE (trace design) — next: W3 D2 (Retry-After ticket + instrumentation/trace viewer CLI)

## Done
- W3 D1: app/agent/trace.py (TraceEvent, TraceSink Protocol, InMemorySink, JsonlFileSink, TraceRecorder);
  AgentLoop(trace=...) explicit emit: run_started, llm_call, tool_call, guard_triggered, run_finished;
  AgentState.run_id; main.py writes traces/runs.jsonl; tests/test_trace.py (11 tests) → 130 tests passed

- W1 D1–D5: LLMClient (ADR-0001), Tool/Registry, native tool calling, AgentLoop,
  error-as-observation, Workspace-restricted list_files/read_file/search_text
- W2 D1: Decision schema + 3 structured-output strategies (reference, not wired)
- W2 D2: Pydantic tool-arg validation
- W2 D3: RetryPolicy, DecisionRecovery, Clock/RuntimeBudget/BudgetTracker, LoopGuard
- W2 D4: Guard integration (TIMEOUT, MAX_ITERATIONS, LOOP_DETECTED)
- W2 D5: Usage/ModelPricing/TokenBudget/UsageTracker, TOKEN_BUDGET_EXCEEDED
- W2 D5.5: validation wired, classify_llm_error, ResilientClient, LLM_FAILED, SDK timeout (max_retries=0)
- Cleanup S1: dead code removed; per-run LoopGuard/BudgetTracker; validation formatter in app/tools/validation.py
- Cleanup S2: Tool.args_model single source of truth; strict_json_schema; ToolArgumentRegistry removed;
  validation mandatory; limits are tool config, not model-facing
- W2 D6: parse_tool_call (never raises), ToolCall.parse_error, malformed args → observation,
  fault-injection suite (tests/test_fault_injection.py, 7 tests) → 113 tests passed
- W2 Cleanup S1 (Hygiene): RuntimeBudget.max_iterations removed; LoopGuard block_on_nth_call rename;
  search_text skips environment/cache dirs (os.walk prune); consecutive malformed-call cap (ConsecutiveCounter);
  loop.py docstring aligned; Decision family removed (git history, commit before 5f600dc);
  tests/test_openai_client.py (6 tests pin SDK contract)
  → 106 passed production
- W2 Cleanup S3 (Layering move): Provider-facing modules moved from app/agent/ to app/llm/
  (retry.py, llm_errors.py, resilient_client.py, usage.py -> types.py, errors.py);
  Layer rules enforced & AST-tested (tests/test_layering.py):
  1) app/agent does not import openai
  2) app/llm does not import app/agent
  3) app/tools imports neither
  Dependency flow: app/agent -> app/llm -> app/tools
  → 109 passed production
- W2 Cleanup S4a (A2 core refactor foundations): Built provider-neutral types & complete adapters side-by-side:
  LLMResponse(text, tool_calls, usage, assistant_items), user_message, assistant_message, tool_result_message;
  OpenAIClient.complete with _to_openai_input & _dump_item; FakeLLMClient.complete;
  ResilientClient.complete (stateless, should_abort parameter); tests/builders.py;
  tests/test_a2_foundations.py (8 tests)
  → 117 passed production
- W2 Cleanup S4b (Loop migration & legacy cleanup): AgentLoop migrated to client.complete(messages, tools, should_abort);
  conversation is provider-neutral JSON-serializable list; ResilientClient stateless;
  LLMClient Protocol (ABC, ask, respond_with_tools, set_deadline_check removed);
  tests migrated; tests/test_a2_loop.py (3 tests)
  → 117 passed production
- Cleanup S5: live verification (reasoning tokens included in output_tokens;
  max_output_tokens is a hard cap that also eats reasoning; replay of reasoning items OK)
- Empty final answer => LLM_FAILED (test_empty_final_answer_is_not_completed, 118 tests passed)
- ADR-0002/0003/0004
- Live 429 TPM RateLimitError observed and verified: classify_llm_error classified as ErrorKind.TRANSIENT,
  exponential backoff correctly surfaced in AttemptRecord attempt log.
- W2 Cleanup S6 (Codebase hygiene, test deduplication & docs):
  - Consolidated duplicate test helpers (FakeClock, FakeSDK, ScriptedClient, function_call_item, usage) into tests/builders.py
  - Removed redundant local helper implementations and inline mocks across 9 test modules (test_a2_foundations, test_agent_loop, test_budget, test_error_recovery, test_fault_injection, test_integration_pass, test_openai_client, test_runtime_guards, test_tools)
  - Hoisted inline imports (httpx, openai, DeadlineExceeded, ToolCall) to module level and cleaned up unused imports across tests and app/llm/openai_client.py
  - Synchronized AgentRunTimeCodeBaseExplain.md: all 35 source code blocks 100% matched with actual implementation; added Section 7 (Test Suite Architecture & Quality Assurance)
  - Full automated verification gate: 119/119 tests passed in 0.90s, mypy clean (34 files); OpenAIClient should_abort wired

## Code state
app/agent/loop.py        AgentLoop(client: LLMClient, registry, executor, max_iterations, runtime_budget, clock,
                         loop_guard_factory, token_budget, pricing, max_consecutive_malformed)
                         run(): provider-neutral conversation; client.complete(messages, tools, should_abort);
                         order: wall-clock → iter → LLM (LLMCallFailed→LLM_FAILED, DeadlineExceeded→TIMEOUT)
                         → usage → final answer → token budget → [per call: parse_error (N consecutive → LOOP_DETECTED) → loop guard → execute]
app/agent/loop_guard.py  LoopGuard(block_on_nth_call), ConsecutiveCounter(limit), call_fingerprint
app/agent/budget.py      RuntimeBudget(max_wall_time_seconds, per_call_timeout_seconds), BudgetTracker
app/agent/cost.py        UsageTracker, ModelPricing, TokenBudget
app/agent/state.py       AgentStatus, AgentState(conversation, iteration, status, final_response, error, history, usage, llm_attempts)
app/llm/client.py        LLMClient(Protocol): complete(messages, tools, should_abort) -> LLMResponse
app/llm/errors.py        LLMCallFailed(attempts, kind, attempt_log), DeadlineExceeded(attempt_log)
app/llm/retry.py         RetryPolicy, ErrorKind, RetryDecision
app/llm/llm_errors.py    classify_llm_error (unknown => PERMANENT)
app/llm/resilient_client.py  ResilientClient(inner, policy, sleep, classify) - completely stateless
app/llm/types.py         AttemptRecord, LLMResponse, Usage, extract_usage, user_message, assistant_message, tool_result_message
app/llm/openai_client.py OpenAIClient: complete(messages, tools, should_abort) with _to_openai_input & _dump_item
app/llm/fake_client.py   FakeLLMClient: complete(), FakeResponse
app/tools/base.py        Tool: name, description, args_model (abstract), input_schema (derived), run(dict)
app/tools/schema_utils.py  strict_json_schema(model)
app/tools/schemas.py     ListFilesArgs{path}, ReadFileArgs{path}, SearchTextArgs{query,path}
app/tools/search_text.py SearchTextTool: SKIP_DIRS pruned via os.walk
app/tools/executor.py    ToolExecutor(registry): mandatory validation via tool.args_model
app/tools/validation.py  format_validation_error(_json)
app/tools/call.py        ToolCall(call_id, tool_name, arguments, parse_error=None)
app/tools/call_parsing.py  parse_tool_call(call_id, name, raw_arguments) -> ToolCall (never raises)
tests/builders.py        Centralized shared test fixtures: FakeClock, FakeSDK, ScriptedClient, function_call_item, usage, make_llm_response
AgentRunTimeCodeBaseExplain.md  Bilingual technical documentation and architecture reference; 100% synchronized with codebase (Sections 1-8)
Decision family learning artifacts removed (preserved in git history, commit before 5f600dc)

## Key design decisions
- Trace = explicit emit through sink Protocol (not derived from state, not logging module)
- tool_call events record arguments + result_chars, never result content (size + secrets)
- Sink failures never break a run (stderr warning); seq gap reveals dropped events
- run_finished emitted once after the loop (covers every terminal status)
- ts = wall-clock UTC for ordering; durations from perf_counter
- Conversation is provider-neutral JSON-serializable list; provider serialization happens strictly in provider client
- ResilientClient is completely stateless; run deadline passed via should_abort callable parameter
- Attempt log travels with LLMResponse.attempts or on raised LLMCallFailed/DeadlineExceeded.attempt_log
- Limits (max_bytes/...) are safety policy → tool config, never model-facing
- Validation mandatory in ToolExecutor; Tool.args_model single source of truth
- Usage None≠0; fail closed; token budget checked before side effects; final answer accepted over budget
- Retry wraps LLM call only; unknown LLM errors PERMANENT; SDK retries disabled
- Model's malformed output is an observation, not a run failure; parse before loop guard; consecutive cap (3)

## Open problems / bugs
- Empty-final-answer path emits no guard_triggered (provider issue, shown in run_finished)
- Per-attempt LLM latency not traced (W3 D2); JsonlFileSink reopens file per event
- Arguments may contain secrets-adjacent paths (W7 D4)
- Retry-After ticket moved to W3 D2 (need live look at RateLimitError.response.headers first)
- [RESOLVED] A1: ABC vs Protocol (ADR-0002) → LLMClient is single Protocol with complete()
- [RESOLVED] A2: internal LLMResponse type + serializable conversation + deadline as call param (should_abort)
- [RESOLVED] A3: exception location → app/llm/errors.py (LLMCallFailed, DeadlineExceeded)
- [RESOLVED] B5: conversation serialization → neutral JSON messages (user, assistant, tool_result)
- [RESOLVED] ResilientClient run-scoped state → stateless; attempt_log travels via response.attempts / exc.attempt_log
- [RESOLVED] B2 LoopGuard naming → block_on_nth_call
- [RESOLVED] A4: search_text skips only .git → SKIP_DIRS os.walk prune; Decision family removed (git history, commit before 5f600dc)
- [RESOLVED] Endless malformed calls not caught by LoopGuard → ConsecutiveCounter cap stops loop
- [RESOLVED] max_iterations duplicated in RuntimeBudget → removed, single source in AgentLoop
- LLMResponse lacks incomplete_reason (provider-truncated responses)
- max_output_tokens not set: needs measured reasoning-token distribution (W3)
- Retry-After + jitter: live Groq TPM 429 observed (RetryPolicy raised to 5 attempts, base 3s, max 25s); W3 ticket #1
- TPM limit & tool output size: 429 TPM exhaustion (Used 7328 / Requested 3350 vs 8000 limit) confirms tool output size is primary input token & cost driver as conversation grows; empirical support for W5 truncation & W9 compression
- Cost report is a lower bound (failed attempts' usage invisible); cached tokens not priced separately
- Replay verified only on Groq gpt-oss-120b, few runs
- Cross-package imports must stay absolute (layering test ignores relative imports)
- Tool.run takes raw dict → typed args ADR in W5; strict_json_schema nested unsupported
- W5 D1: read_file needs model-facing offset/limit; keep max_bytes as safety cap
- B7 failed-attempt usage not tracked; dangling function_call after budget stop (W12)
- Workspace allows read_file(".env") (W7 D4)
- Unverified agent claims → eval grader (W3)

## Things I don't understand yet
(ကိုယ့်ဘာသာဖြည့်ပါ)

## Eval status
No formal eval yet (Week 3).
W3 D1 live trace run (run_id: 157dd5c2ea03414bb8d15af61be97ef8):
- 19 events, 8 iterations, status: completed.
- 8 LLM calls: latency ranged 477ms - 25,976ms (the final call had 4 attempts due to TPM rate-limit backoff, user-visible latency ~26s).
- 7 tool calls: execution duration ~0.01ms - 7.26ms (sub-millisecond for local directory listings, ~7ms for README read).
- Input token progression: 325 → 448 → 505 → 554 → 632 → 943 → 1,000 → 1,904 → 4,625 (driven by cumulative tool result history).
- Total tokens: 12,440 (cost: $0.002543).
Baseline W2 D5 Exp 1: 6 calls, 5481 in / 1153 out, $0.0015; fixed overhead 301 input tokens (3 tools).
Cleanup S1 live: 7 calls, 7236 in / 1245 out, $0.0018.
Input growth driven by tool-output size, not call count. Reasoning tokens verified included in output_tokens (ADR-0002).
D6 Exp 1 (test-first, before fix): 4 failed (test_garbage_json_arguments_become_observation, test_non_object_arguments_become_observation, test_malformed_calls_do_not_trigger_loop_guard, test_endless_malformed_calls_stop_at_max_iterations), 3 passed.
D6 Exp 2 (after fix): 7/7 fault injection tests passed; 113 passed total in test suite.
D6 Exp 3 (live run): completed successfully.

## Today's goal (next session)
W3 D2 (Retry-After ticket + instrumentation/trace viewer CLI)

