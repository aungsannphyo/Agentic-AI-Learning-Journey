# PROGRESS

## Current: Week 2 / Day 6 DONE (next: Week 3 / Day 1 = trace design, after A2 prep)    Date: 2026-10-05

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

## Code state
app/agent/loop.py        AgentLoop(client, registry, executor, max_iterations, runtime_budget, clock,
                         loop_guard_factory, token_budget, pricing)
                         run(): per-run tracker/guard; client.set_deadline_check if present
                         order: wall-clock → iter → LLM (LLMCallFailed→LLM_FAILED, DeadlineExceeded→TIMEOUT)
                         → usage → final answer → token budget → [per call: parse_error → loop guard → execute]
app/agent/resilient_client.py  ResilientClient(inner, policy, sleep, classify); set_deadline_check(); attempt_log
app/agent/llm_errors.py  classify_llm_error (unknown => PERMANENT)
app/agent/cost.py, usage.py    UsageTracker, ModelPricing, TokenBudget, extract_usage
app/agent/state.py       AgentStatus: RUNNING, COMPLETED, MAX_ITERATIONS, TIMEOUT, LOOP_DETECTED,
                         TOKEN_BUDGET_EXCEEDED, LLM_FAILED
app/tools/base.py        Tool: name, description, args_model (abstract), input_schema (derived), run(dict)
app/tools/schema_utils.py  strict_json_schema(model)
app/tools/schemas.py     ListFilesArgs{path}, ReadFileArgs{path}, SearchTextArgs{query,path}
app/tools/executor.py    ToolExecutor(registry): mandatory validation via tool.args_model
app/tools/validation.py  format_validation_error(_json)
app/tools/call.py        ToolCall(call_id, tool_name, arguments, parse_error=None)
app/tools/call_parsing.py  parse_tool_call(call_id, name, raw_arguments) -> ToolCall (never raises)
app/llm/openai_client.py ask, respond_with_tools (timeout_seconds, max_retries=0)
app/llm/fake_client.py   FakeLLMClient(response, response_sequence), FakeResponse.usage

## Key design decisions
- Limits (max_bytes/...) are safety policy → tool config, never model-facing
- Validation mandatory in ToolExecutor; Tool.args_model single source of truth
- Usage None≠0; fail closed; token budget checked before side effects; final answer accepted over budget
- Retry wraps LLM call only; unknown LLM errors PERMANENT; SDK retries disabled
- Model's malformed output is an observation, not a run failure; parse before loop guard
- Per-run state via factories; ResilientClient run-scoped state is a known compromise

## Open problems / bugs
- A2: internal LLMResponse type + serializable conversation (before W3 D1); deadline as call param
- A1: ABC vs Protocol (ADR-0002); A3 exception location; B2 LoopGuard naming
- A4: search_text skips only .git (not .venv/__pycache__); Decision family README note
- Endless malformed calls not caught by LoopGuard (only max_iterations)
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