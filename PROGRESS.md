# PROGRESS

## Current: Week 3 / Day 2 DONE (151 tests, ruff+mypy clean) — next: W3 D3 (eval task set)

## Done
- W3 D2: retry_after_seconds() (header, then "try again in Ns" message; transient only);
  ResilientClient(max_retry_after_seconds=60): delay=max(backoff,hint), hint>max → fail fast;
  AttemptRecord(+retry_after_seconds, +latency_ms); llm_call/guard_triggered trace events carry attempt_log;
  app/trace_view.py (python -m app.trace_view [run_id|prefix|latest] [--list] [--file]);
  tests/test_retry_after.py (12), tests/test_trace_view.py (9) → 151 passed total
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
                         loop_guard_factory, token_budget, pricing, max_consecutive_malformed, trace)
                         run(): provider-neutral conversation; client.complete(messages, tools, should_abort);
                         order: wall-clock → iter → LLM (LLMCallFailed→LLM_FAILED, DeadlineExceeded→TIMEOUT)
                         → usage → final answer → token budget → [per call: parse_error (N consecutive → LOOP_DETECTED) → loop guard → execute]
                         attempt_log included in llm_call and guard_triggered timeout events
app/agent/loop_guard.py  LoopGuard(block_on_nth_call), ConsecutiveCounter(limit), call_fingerprint
app/agent/budget.py      RuntimeBudget(max_wall_time_seconds, per_call_timeout_seconds), BudgetTracker
app/agent/cost.py        UsageTracker, ModelPricing, TokenBudget
app/agent/state.py       AgentStatus, AgentState(conversation, iteration, status, final_response, error, history, usage, llm_attempts)
app/agent/trace.py       TraceEvent, TraceSink, InMemorySink, JsonlFileSink, TraceRecorder
app/trace_view.py        Read-only viewer CLI for traces/runs.jsonl (decoupled, plain JSONL dicts)
app/llm/client.py        LLMClient(Protocol): complete(messages, tools, should_abort) -> LLMResponse
app/llm/errors.py        LLMCallFailed(attempts, kind, attempt_log), DeadlineExceeded(attempt_log)
app/llm/retry.py         RetryPolicy, ErrorKind, RetryDecision
app/llm/llm_errors.py    classify_llm_error, retry_after_seconds (header first, then message regex)
app/llm/resilient_client.py  ResilientClient(inner, policy, sleep, classify, max_retry_after_seconds):
                         delay=max(backoff, hint), fail-fast if hint > max_hint; tracks latency_ms
app/llm/types.py         AttemptRecord(+retry_after_seconds, +latency_ms), LLMResponse, Usage, extract_usage,
                         user_message, assistant_message, tool_result_message
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
AgentRunTimeCodeBaseExplain.md  Bilingual technical documentation and architecture reference
Decision family learning artifacts removed (preserved in git history, commit before 5f600dc)

## Key design decisions
- Retry hint is a transport concern → lives in ResilientClient, not RetryPolicy
- Hint wins only upward (max with backoff); over-long hint fails fast, never sleeps
- Viewer reads plain JSONL dicts (no runtime imports); old traces still render
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
- RESOLVED: Retry-After ticket (header path verified live: Groq returns `retry-after: 16` HTTP header; message path covered by tests)
- Sleep is not remaining-wall-clock aware (should_abort is a bool, not remaining time)
- Message regex tied to Groq wording; trace has no schema_version
- attempt_log error text (200 chars) may echo provider error bodies (secret check Exp 5: clean, no leaks found)
- Empty-final-answer path emits no guard_triggered (provider issue, shown in run_finished)
- Arguments may contain secrets-adjacent paths (W7 D4)
- LLMResponse lacks incomplete_reason (provider-truncated responses)
- max_output_tokens not set: needs measured reasoning-token distribution (W3)
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
- Probe result (headers present? parsed retry_after?): Headers present (`retry-after: 16`), parsed retry_after=16.0 (live verified against Groq 429).
- Viewer on live run: llm share=100% (11.01s / 11.02s wall) / slowest call=iter 5 (7869ms, retries=1) / retries=1.
- Day 1 trace rendering: 8 iterations, 56.01s LLM time (100% wall share), slowest call iter 7 (51002ms, 4 retries).
- No `gsk_` or `Bearer` tokens leaked in traces (checked via Select-String regex).

## Today's goal (next session)
W3 D3 (eval task set)


