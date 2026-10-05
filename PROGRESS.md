# PROGRESS

## Current: Week 2 Cleanup Step 4b DONE    Date: 2026-10-05

## Done
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
  loop.py docstring aligned; Decision family moved to experiments/week2_structured_output/;
  tests/test_openai_client.py (6 tests pin SDK contract)
  → 106 passed production, 17 passed experiments
- W2 Cleanup S3 (Layering move): Provider-facing modules moved from app/agent/ to app/llm/
  (retry.py, llm_errors.py, resilient_client.py, usage.py -> types.py, errors.py);
  Layer rules enforced & AST-tested (tests/test_layering.py):
  1) app/agent does not import openai
  2) app/llm does not import app/agent
  Dependency flow: app/agent -> app/llm -> app/tools
  → 109 passed production, 17 passed experiments
- W2 Cleanup S4a (A2 core refactor foundations): Built provider-neutral types & complete adapters side-by-side:
  LLMResponse(text, tool_calls, usage, assistant_items), user_message, assistant_message, tool_result_message;
  OpenAIClient.complete with _to_openai_input & _dump_item; FakeLLMClient.complete;
  ResilientClient.complete (stateless, should_abort parameter); tests/builders.py;
  tests/test_a2_foundations.py (8 tests)
  → 117 passed production, 17 passed experiments
- W2 Cleanup S4b (Loop migration & legacy cleanup): AgentLoop migrated to client.complete(messages, tools, should_abort);
  conversation is provider-neutral JSON-serializable list; ResilientClient stateless;
  LLMClient Protocol (ABC, ask, respond_with_tools, set_deadline_check removed);
  tests migrated; tests/test_a2_loop.py (3 tests)
  → 117 passed production, 17 passed experiments

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
app/llm/openai_client.py OpenAIClient: complete() with _to_openai_input & _dump_item
app/llm/fake_client.py   FakeLLMClient: complete(), FakeResponse
app/tools/base.py        Tool: name, description, args_model (abstract), input_schema (derived), run(dict)
app/tools/schema_utils.py  strict_json_schema(model)
app/tools/schemas.py     ListFilesArgs{path}, ReadFileArgs{path}, SearchTextArgs{query,path}
app/tools/search_text.py SearchTextTool: SKIP_DIRS pruned via os.walk
app/tools/executor.py    ToolExecutor(registry): mandatory validation via tool.args_model
app/tools/validation.py  format_validation_error(_json)
app/tools/call.py        ToolCall(call_id, tool_name, arguments, parse_error=None)
app/tools/call_parsing.py  parse_tool_call(call_id, name, raw_arguments) -> ToolCall (never raises)
experiments/week2_structured_output/ Decision family learning artifacts (17 tests)

## Key design decisions
- Conversation is provider-neutral JSON-serializable list; provider serialization happens strictly in provider client
- ResilientClient is completely stateless; run deadline passed via should_abort callable parameter
- Attempt log travels with LLMResponse.attempts or on raised LLMCallFailed/DeadlineExceeded.attempt_log
- Limits (max_bytes/...) are safety policy → tool config, never model-facing
- Validation mandatory in ToolExecutor; Tool.args_model single source of truth
- Usage None≠0; fail closed; token budget checked before side effects; final answer accepted over budget
- Retry wraps LLM call only; unknown LLM errors PERMANENT; SDK retries disabled
- Model's malformed output is an observation, not a run failure; parse before loop guard; consecutive cap (3)

## Open problems / bugs
- [RESOLVED] A1: ABC vs Protocol (ADR-0002) → LLMClient is single Protocol with complete()
- [RESOLVED] A2: internal LLMResponse type + serializable conversation + deadline as call param (should_abort)
- [RESOLVED] A3: exception location → app/llm/errors.py (LLMCallFailed, DeadlineExceeded)
- [RESOLVED] B5: conversation serialization → neutral JSON messages (user, assistant, tool_result)
- [RESOLVED] ResilientClient run-scoped state → stateless; attempt_log travels via response.attempts / exc.attempt_log
- [RESOLVED] B2 LoopGuard naming → block_on_nth_call
- [RESOLVED] A4: search_text skips only .git → SKIP_DIRS os.walk prune; Decision family moved to experiments/
- [RESOLVED] Endless malformed calls not caught by LoopGuard → ConsecutiveCounter cap stops loop
- [RESOLVED] max_iterations duplicated in RuntimeBudget → removed, single source in AgentLoop
- Tool.run takes raw dict → typed args ADR in W5; strict_json_schema nested unsupported
- W5 D1: read_file needs model-facing offset/limit; keep max_bytes as safety cap
- B7 failed-attempt usage not tracked; dangling function_call after budget stop (W12)
- max_output_tokens not set; Retry-After/jitter missing
- Workspace allows read_file(".env") (W7 D4)
- Unverified agent claims → eval grader (W3)

## Things I don't understand yet
(ကိုယ့်ဘာသာဖြည့်ပါ)

## Eval status
No formal eval yet (Week 3).
Baseline W2 D5 Exp 1: 6 calls, 5481 in / 1153 out, $0.0015; fixed overhead 301 input tokens (3 tools).
Cleanup S1 live: 7 calls, 7236 in / 1245 out, $0.0018.
Input growth driven by tool-output size, not call count. Reasoning-token accounting unverified.
D6 Exp 1 (test-first, before fix): 4 failed (test_garbage_json_arguments_become_observation, test_non_object_arguments_become_observation, test_malformed_calls_do_not_trigger_loop_guard, test_endless_malformed_calls_stop_at_max_iterations), 3 passed.
D6 Exp 2 (after fix): 7/7 fault injection tests passed; 113 passed total in test suite.
D6 Exp 3 (live run): completed successfully.

## Today's goal (next session)
A2 prep: internal LLMResponse type + serializable conversation, then W3 D1 trace design.