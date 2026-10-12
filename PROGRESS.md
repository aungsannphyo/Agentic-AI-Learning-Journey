# PROGRESS

## Current: W4 D6 DONE (278 passed, 3 xfailed) — next: W5 D1 (Agent-Computer Interface design)

## Done
- W4 D6: positive_control category + 3 tasks (pos-order-limit-enforced, pos-discount-range,
  pos-stock-shortage); RunRecord.answer stored in full (no [:600]); refusal grader hardened (AST fixture
  identifier allowlist + pointer-verb detection), EVAL_VERSION=4; tests: 3 false-fail guards, 3 xfail
  known limitations (indirect prose fabrication); v0.6-noprog2-neg offline re-graded (regraded_from: 3), 5/6.
- E15-off (positive controls, N=3 each): 8/9 pass; empty-streak>=2 in 3/9 (discount-range 0/3: prompt
  contains 'discount').
- E15-on (--no-progress 2): 8/9 pass; nudge fired 2/9 (order-limit #2 -> recovered by file browsing, true
  pass; stock-shortage #1 -> cap 8/8). False give-up 0/2 fired runs (0/9 total). H19' met, H21 met but
  effective N=2; run-to-run variance changed which runs fired.
- stock-shortage #1 audit: tool-name hallucination (repo_browser.list_files) cost 1 turn; over-verification
  after finding OutOfStockError cost 2 turns -> cap. Not a nudge-induced give-up; nudge did not prevent it.
- W4 comparison note written (reactive vs planned; see summary).
- W4 D5: app/agent/nudges.py trailing_empty_searches (read_file success resets, list_files transparent),
  no_progress_nudge (capped query list, refusal guidance). AgentLoop(no_progress_after=None): user note
  appended when empty search streak >= N and grew since last nudge; trace event no_progress_nudged.
  evals/run.py --no-progress N (label noprog{N}). tests: test_no_progress.py (7), test_loop_no_progress.py (4).
- Threshold selection: shop fixture negative runs streak >= 3 was 45.8% (evaded by read_file reset),
  streak >= 2 was 95.8% (positive tasks 1/60 = 1.7%). Pre-registered threshold locked at 2.
- E13 live eval (negative x noprog2, N=3 each): completed 5/6 (baseline 0/6), tokens mean 2,464/run (-51% vs
  baseline ~5k), 0 429s (14,786 total). H17' CONFIRMED (5/6 >= 4/6, one-sided Fisher p = 6/792 ≈ 0.0076, N=12,
  2 negative tasks only), H20' CONFIRMED (token <= 5k). All 5 nudged runs immediately produced refusal on next turn.
- Grader fix & EVAL_VERSION bump to 3: no_invented_path made basename-aware (_is_real_path via rglob *.py);
  run 1 false-fail ('orders.py' without src/) resolved to true pass. Re-graded offline: pass 4/6 (67%) -> 5/6 (83%)
  (completed rate was already 5/6; both being 5/6 is coincidental, not identical metrics).
  tests/test_graders.py (+2 regression & negative tests) -> 263 passed; ruff/mypy clean.
- Run 5 audit: read_file reset evasion confirmed (1/6 runs): agent called search_text only once, spent turns
  browsing/reading files (read_file reset streak to 0), evading nudge and hitting max_iterations 8/8.
- W4 D4: app/agent/nudges.py (trailing_failures, failure_nudge, EMPTY_ANSWER_NUDGE; pure fns).
  AgentLoop(failure_nudge_after=None, retry_empty_answer=False): failure nudge appended as user note when
  tail failure streak >= N and grew since last nudge (AgentState.last_nudged_failures, reset on success);
  empty-answer retried once (AgentState.empty_answer_retries), consumes an iteration; second empty ->
  LLM_FAILED. Trace events failure_nudged / empty_answer_nudged. evals/run.py --failure-nudge N, --retry-empty.
  tests: test_nudges.py (5), test_loop_nudges.py (7) -> 250 passed; ruff/mypy clean.
- Audit: model-output-malformation killed 2 runs of ~87 in two forms: v0.3-capture HTTP 400 tool_use_failed
  (hallucinated 'repo_browser'), v0.5-ledger-neg empty answer (args leaked into reasoning).
- Manipulation check: runs with >=2 consecutive tool failures = 0/179 (streak 1: 13 runs). Live eval of
  failure nudge NOT run (treatment would not fire).
- W4 D3: T3 evidence ledger. app/agent/ledger.py build_ledger(records)->str|None (files read, searches+match
  count, failed calls; capped; code-derived from state.history, never model claims). AgentLoop(ledger_every=None):
  after tool round, every N iterations append a user "System note (not from the user)" message (append-only);
  trace event ledger_added. evals/run.py --ledger-every N (label ledger{N}); EVAL_VERSION unchanged (2).
  tests: test_ledger.py (11), test_loop_ledger.py (5) -> 238 passed (+16; 10 planned + 6 extra edge cases).
- E10 probe: Groq Responses accepts a user message appended after function_call_output (turn2 OK).
- E11 (negative x ledger3, N=3 each): 0/6 pass; 5/6 max_iterations, 1/6 llm_failed; ledger_added 11; 28,248 tok.
  H11 null result (same as baseline 0/6): ledger is not a stopping rule.
- negative-email #1 llm_failed audit: iter-3 reasoning contained '{"path":"src"}' text, no structured
  function_call, empty text -> malformed tool-call glitch, NOT ledger misreading (my placement hypothesis
  rejected). Rate 1/14 ledger injections; baseline rate unmeasured.
- E12 (explain-orders + explain-stock-check x ledger3, N=3): stock-check 3/3 (ledger_added 3), explain-orders
  0/3 at iteration 0 (no ledger fired), llm_failed 0/6, 20,090 tok.
- W4 D2: probe (scripts/peek_nested_schema.py): Groq Responses text.format accepts flat AND nested strict
  schema; tools=[] calls still return a reasoning item. (Probed text.format only, NOT tool-arg strict schema.)
- Plan as data: app/agent/plan.py (Plan, PlanStep, StepStatus; ids/status assigned by code),
  app/agent/plan_parsing.py (defensive numbered-list parser, currently unused fallback),
  app/agent/planner.py (PlanSpec{steps:list[str]}, Planner.make -> PlanOutcome; tools=[], output_schema),
  prompts.PLANNER_V1 (not in PROMPTS/--prompt choices).
- LLMClient.complete(..., output_schema=None) -> OpenAIClient text.format json_schema strict; tools kwarg
  only sent when non-empty; ResilientClient forwards; FakeLLMClient.output_schemas.
- AgentLoop(use_plan, max_plan_steps): planner call before loop; plan injected into conversation[0];
  planner usage recorded in state.usage; planner transport/parse failure -> plan_failed trace, run continues
  without plan. Trace events plan_created / plan_failed; trace_view renders plan lines.
- evals/run.py --plan (agent_label = prompt.label+planner-v1.label); EVAL_VERSION unchanged (2).
- tests/test_planner.py (6) -> 222 passed; ruff/mypy clean.
- E8 (explain-orders, plan-on, N=3): 3/3 pass, ~6.0k tok/run, plan_failed 0/3. Iter-0 reasoning now
  "follow plan: list files..." (no "no need to access code"). Only 1/3 runs read config.py.
- E9 (negative-payment/email, plan-on, N=3 each): 0/6 pass, 6/6 max_iterations (8/8), plan_failed 0/6,
  36,325 tok (~6.05k/run, +~22% vs ~4.9k baseline). H8 CONFIRMED: plan does not create a stopping criterion.
- W4 D1: prompt versioning (app/agent/prompts.py: Prompt name/sha/label; BASELINE byte-identical to v0.2
  [baseline@dd04b6a4]; GROUNDED_V1 = baseline + grounding rule [grounded-v1@284f3dcd]); evals/run.py --prompt,
  agent_label defaults to prompt.label, per-version trace file; main.py AGENT_PROMPT env.
- E2: prompt-driven visible thought (option B) INVALID on Groq: 0/31 turns; text before tool call -> 400
  output_parse_failed. react-v1/react-grounded-v1 removed.
- Step 0 probe (scripts/peek_items.py): gpt-oss-120b Responses API returns type:"reasoning" item
  (summary=[], content[].reasoning_text) on tool-call turns. Option A' adopted: app/llm/reasoning.py
  extract_reasoning -> LLMResponse.reasoning; AgentState.thoughts; trace llm_call `thought` (500 cap);
  trace_view renders it; scripts/reasoning_stats.py. Coverage 151/154 (98%), mean 146 chars, 0 truncated.
- E4 regression guard: v0.3-capture 78% vs v0.2b 75%; diff is solely explain-orders run #2 (1 pass of 3).
  Other 11 tasks identical. Token +4.0% fully explained by that run.
- E6: baseline explain-orders iter-0 reasoning: "No need to access code. So just answer." (model reads
  prompt as generic e-commerce question).
- E7 (explain-orders only, N=5, grounded-v1): 5/5 pass, iterations 5-6, tokens 5.2-6.3k. Iter-0 reasoning:
  "We need to locate code that computes order total. Let's search." H2''' PASSED (baseline pooled 1/6),
  H6 mechanism CONFIRMED via trace events: orders.py (5/5), pricing.py (5/5), config.py (4/5; run 05fcd0f2
  answered after pricing.py; grader passed via must_read=[orders.py]).
- Stats: explain-orders baseline pooled 1/6 vs grounded 5/5, one-sided Fisher p = 6/462 ~ 0.013 (N=11, small; report as large effect, not proof)
- Grader gap: run 05fcd0f2 passed without reading config.py; must_read=[orders.py] too weak -> W4 D6 audit (eval_version bump if changed)
- Full 72-run E7 aborted by Groq TPD (200k/day) 429; ResilientClient fail-fast (hint > 60s) worked.
  v0.3-grounded(.b).json renamed .invalid.
- W3 D6: grader fix (trailing-zero decimals, test-first), explain-orders must_read=[orders.py],
  EVAL_VERSION=2 in spec.py, report fields eval_version/agent_label, compare warns on eval_version mismatch,
  tests +3 → 199 passed total
- Baseline v0.2 (corrected eval): 75% overall pass rate (27/36 runs, 97,829 tokens, $0.0209); find_file 100%, find_symbol 100%, read_fact 100%, explain 50%, negative 0%
- W3 D5: evals/runner.py (run_task_once temp-copy isolation, run_suite N repeats + token-based cooldown,
  summarize/flaky, build_report), evals/compare.py, evals/run.py (python -m evals.run [--version --repeats --task --compare]),
  Makefile; entity blocklist for negative tasks; tests/test_eval_runner.py (13 tests) → 196 passed total
- Baseline v0.1: 64% overall pass rate (36 runs, 98,489 tokens, $0.0210); find_file 100%, find_symbol 100%, explain 50%, read_fact 56%, negative 0%
- W3 D4: evals/graders.py (RunResult, Check, Grade, grade(), contains_word word-boundary);
  spec: Expect.forbidden + kind "refusal"; tasks.yaml: find-discount-file forbidden legacy_pricing,
  negative tasks → kind refusal; tests/test_graders.py (18 tests) → 183 passed total
- W3 D3: evals/fixtures/shop (synthetic repo, 8 files: src 6 incl. decoy legacy_pricing.py, tests 1, README 1);
  evals/tasks.yaml (13 tasks: 12 enabled + 1 disabled edit; categories find_file/read_fact/find_symbol/explain/negative/edit);
  evals/spec.py (pydantic TaskFile/Task/Expect, load_tasks, referenced_paths);
  tests/test_eval_tasks.py (13 tests) + test_layering.py rule 4 (1 test) → 165 passed total
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
app/agent/plan.py        Plan, PlanStep, StepStatus (ids/status assigned by code)
app/agent/plan_parsing.py parse_numbered_steps (defensive fallback parser)
app/agent/planner.py     PlanSpec, PlanOutcome, Planner.make (tools=[], output_schema)
app/agent/prompts.py     Prompt, BASELINE, GROUNDED_V1, PLANNER_V1, PROMPTS, get_prompt
app/llm/reasoning.py     extract_reasoning(items) -> str (only place that knows reasoning item shape)
app/llm/types.py         LLMResponse.reasoning: str = ""
app/agent/loop.py        AgentLoop(client, registry, executor, max_iterations, runtime_budget, clock,
                         loop_guard_factory, token_budget, pricing, max_consecutive_malformed, trace,
                         use_plan=False, max_plan_steps=6)
                         run(): [planner call if use_plan -> plan injected into conversation[0]] then loop;
                         _record_thought (response.reasoning, every turn incl. final); llm_call trace carries `thought`;
                         _make_plan emits plan_created / plan_failed
app/agent/state.py       AgentStatus, AgentState(conversation, iteration, status, final_response, error, history,
                         usage, llm_attempts, run_id, thoughts: list[Thought], plan: Plan | None)
app/agent/loop_guard.py  LoopGuard(block_on_nth_call), ConsecutiveCounter(limit), call_fingerprint
app/agent/budget.py      RuntimeBudget(max_wall_time_seconds, per_call_timeout_seconds), BudgetTracker
app/agent/cost.py        UsageTracker, ModelPricing, TokenBudget
app/agent/trace.py       TraceEvent, TraceSink, InMemorySink, JsonlFileSink, TraceRecorder
app/trace_view.py        Read-only viewer CLI for traces/runs.jsonl (decoupled, plain JSONL dicts)
app/llm/client.py        LLMClient(Protocol): complete(messages, tools, should_abort, output_schema=None)
scripts/peek_items.py    throwaway provider-shape probe; scripts/reasoning_stats.py; scripts/peek_nested_schema.py
app/llm/errors.py        LLMCallFailed(attempts, kind, attempt_log), DeadlineExceeded(attempt_log)
app/llm/retry.py         RetryPolicy, ErrorKind, RetryDecision
app/llm/llm_errors.py    classify_llm_error, retry_after_seconds (header first, then message regex)
app/llm/resilient_client.py  ResilientClient(inner, policy, sleep, classify, max_retry_after_seconds):
                         delay=max(backoff, hint), fail-fast if hint > max_hint; tracks latency_ms
app/llm/types.py         AttemptRecord(+retry_after_seconds, +latency_ms), LLMResponse, Usage, extract_usage,
                         user_message, assistant_message, tool_result_message
app/llm/openai_client.py OpenAIClient: complete(messages, tools, should_abort, output_schema=None);
                         tools kwarg only when non-empty; output_schema -> text.format json_schema strict
app/llm/fake_client.py   FakeLLMClient: complete(), FakeResponse, tracks output_schemas
app/tools/base.py        Tool: name, description, args_model (abstract), input_schema (derived), run(dict)
app/tools/schema_utils.py  strict_json_schema(model)
app/tools/schemas.py     ListFilesArgs{path}, ReadFileArgs{path}, SearchTextArgs{query,path}
app/tools/search_text.py SearchTextTool: SKIP_DIRS pruned via os.walk
app/tools/executor.py    ToolExecutor(registry): mandatory validation via tool.args_model
app/tools/validation.py  format_validation_error(_json)
app/tools/call.py        ToolCall(call_id, tool_name, arguments, parse_error=None)
app/tools/call_parsing.py  parse_tool_call(call_id, name, raw_arguments) -> ToolCall (never raises)
evals/spec.py            TaskFile, Task, Expect(kind, values, path, forbidden), load_tasks, referenced_paths
evals/graders.py         RunResult(status, answer, read_paths, fixture_dir, workspace_dir), Check, Grade,
                         contains_word(text, value) [word-boundary regex], grade(task, result)
evals/runner.py          RunRecord, TaskSummary, read_paths_from, to_run_result, run_task_once, cooldown_for,
                         run_suite(repeats, cooldown, pacing), summarize, category_pass_rates, build_report
evals/compare.py         load_report, compare(old, new)
evals/run.py             CLI for running eval suites and comparing reports (python -m evals.run)
Makefile                 eval, test targets
tests/builders.py        Centralized shared test fixtures: FakeClock, FakeSDK, ScriptedClient, function_call_item, usage, make_llm_response
AgentRunTimeCodeBaseExplain.md  Bilingual technical documentation and architecture reference
Decision family learning artifacts removed (preserved in git history, commit before 5f600dc)

## Key design decisions
- no-progress stays default-off (precision evidence N=2)
- Report effective N (treatment-fired subset), never headline N
- Heuristic graders ship with strict xfail tests documenting known limits
- Give-up policy = advisory nudge on consecutive empty searches (R1 mechanism), code-triggered; model
  decides to conclude absence (never hard stop termination)
- no_progress threshold tuned to 2 for shop fixture; default-off due to unmeasured precision cost on positive tasks
- EVAL_VERSION bumped to 3 due to basename-aware refusal grader fix
- Replan = R1 nudge (append-only user note), code-triggered on objective signals; R2 planner re-run and R3
  model-edited plan not built
- failure_nudge wording never suggests concluding absence (stopping criterion belongs to D5)
- Retry budgets: empty-answer retry capped at 1 AND consumes iteration budget
- Mechanisms without measured benefit ship default-off
- Ledger = objective code-derived progress note, append-only user message, cadence-triggered; model decides
  step done/not (T3 over T1 model-reported / T2 code-inferred)
- StepStatus (D2) currently unused; keep for D4 replanning, drop if still unused after D4
- Plan = agent config flag (--plan), independent of --prompt; one variable at a time
- Plan is advisory context, never control flow; planner failure degrades to no-plan (traced), never stops the run
- Model-facing plan schema minimal (steps: list[str]); id/status are code bookkeeping
- output_schema is a provider-neutral param on LLMClient; text.format shape lives only in OpenAIClient
- Executor = existing loop (E1); step isolation deferred to D3
- Reasoning = native provider trace (raw CoT), not ReAct "thought"; log only, never control flow
- Provider item shape confined to app/llm/reasoning.py; loop sees only LLMResponse.reasoning: str
- Capture is observability-only (E4 guard passed)
- One variable per prompt variant; grounded-v1 NOT default until regression-checked on other categories
- Probe provider capabilities empirically before designing around them
- Pre-register thresholds before running; changing N before the run is allowed, after is not
- eval_version is bumped by hand when graders/tasks change meaning; compare warns on mismatch
- Baselines are only valid at a given eval_version; v0.1 (eval_version 1) is not a baseline
- Client injected via factory; fixture copied per run; grade before workspace is deleted
- Pacing: sequential + cooldown=max(base, tokens/TPM*60); header-aware pacing deferred
- Compare threshold 20% (noise at N=3); noise floor measured by running same code twice
- Grader is a pure function over RunResult (no AgentState); runner adapts state → RunResult (D5)
- passed = all checks; score = fraction passed (partial credit separates "answered but didn't read")
- Incomplete runs (status != completed) fail without answer evaluation
- No LLM-as-judge in W3: deterministic first, measure residual error, then decide
- read_paths = successful read_file calls only (from state.history)
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
- Synthetic immutable fixture (ground truth controlled; small to fit TPM 8000); real-repo tasks added in W5
- Ground truth is tested against the fixture (drift fails CI); must_read catches "answered without reading"
- negative category added to measure hallucination (not just retrieval)
- Edit task pre-registered as enabled:false until W6; baselines use enabled_tasks() only
- Dependency direction: evals may import app, never the reverse

## Open problems / bugs
- v0.7 full baseline (eval_version 4, 15 tasks x N=3 ~120k tokens) NOT run: needs console TPD >= 150k;
  without it, plan/ledger/grounded/no-progress on ceiling tasks (H9/H12/H19) remain UNTESTED
- Over-verification after evidence found: new stopping failure mode; no-progress signal does not cover it
- repo_browser.* tool-name hallucination recurring: try positive tool-name prompt variant
- Positive-control coverage thin (effective N=2); discount-range task not a control
- 2x2 (grounded x plan) attribution still open
- TPD remaining never verified from console (headers show TPM only)
- Failure nudge benefit unmeasured; trigger frequency 0/179 on shop fixture -> need fault-injection tasks
  (D6/W7); eval population lacks recovery-requiring tasks
- Empty-answer retry unmeasurable live (~1-2% rate); unit-tested only
- Provider 400 tool_use_failed still PERMANENT; reopen with more frequency data (error classification ADR)
- Replanning (R2) deferred until a trigger can fire in eval
- Ledger and nudges unmeasured benefit; StepStatus still unused (drop after D5 if unused)
- H13 UNTESTED: explain-orders never reached iteration 3 under baseline prompt, ledger never fired
- Ledger benefit unmeasured: mechanism works; need ledger on/off on explain-orders with grounded-v1
  (iterations 5-6), metric = config.py read rate; N=5 each (~55k)
- Malformed tool call in reasoning text -> empty answer -> LLM_FAILED: count baseline rate in old traces;
  consider retry/nudge on empty-answer-without-tool-calls (revisits W2 "empty final answer => LLM_FAILED")
- Unknown whether model uses ledger content (reasoning did not quote it in the one audited run)
- Ledger omits list_files and truncated search counts (max_results=50)
- H7 only indicative: plan-on 3/3 vs baseline pooled 1/6 (N=3); confounded with grounding rule (grounded-v1
  also 5/5). Need 2x2 (grounded x plan) to attribute.
- H9 UNTESTED: plan-on effect on 8 ceiling tasks (find/read/symbol); plan-on NOT default until tested
- Plan adherence incomplete (config.py read 1/3 despite plan step) -> motivates D3 step tracking
- EVAL_VERSION 4 bump: v0.2b/v0.3-capture baselines are eval_version 2; v0.6 is eval_version 4 (regraded_from: 3);
  compare tool warns on mismatch. Runner now stores full raw answer in RunRecord, ensuring future re-grades retain full evidence.
- read_file reset evasion: Run 5 trace confirmed model called search_text only once, spent remaining turns browsing
  and reading files without query terms, evading no-progress nudge and hitting max_iterations 8/8.
  Backlog: signal = search-only; file-browsing evasion observed 1/6 (needs reset refinement or browsing-aware signal).
- pos-discount-range broad search evasion: prompt keyword 'discount' caused immediate match on turn 1 in 6/6 runs;
  positive-control effective N=2 nudged runs in E15-on (pos-order-limit and pos-stock-shortage). Needs keyword hardening
  if discount task is retained as weak-query control.
- search_text 50 results cap & case-insensitive substring search: treating "0 matches" as conclusive absence is safe
  on small synthetic fixtures, but dangerous on real repos (W5) where pagination/cap or query framing can cause false negatives.
- Refusal grader hardening & known limitations: POINTER_VERBS regex + AST allowlist catches explicit module/service pointers;
  indirect prose fabrication without explicit pointer verbs (e.g. 'likely implemented by the gateway layer') passes heuristic
  grader and is tracked via 3 xfail tests.
- RESOLVED: Precision cost of no_progress on positive controls: H19' met on aggregate (8/9 on vs 8/9 off) and
  H21 met (false give-up 0/2 fired runs, 0/9 total). Model resisted nudge give-up pressure ("say so clearly in your
  final answer") and pivoted to file browsing. However, effective N=2 is too thin to prove precision safety;
  fired subset pass rate was 1/2 (1 hit 8/8 cap); no_progress remains default-off due to unmeasured precision at scale.
- Token +22% on negative attributed to planner call + plan replay: unverified split
- Nested strict schema for TOOL ARGS still UNPROBED (W5 Edit/MCP); strict_json_schema still rejects $defs
- Groq TPD 200k/day ceiling: plan full-suite (~115k) only after Groq console check (remaining >= 150k); rolling vs fixed reset unverified
- Noise floor: >= 1 run observed (explain-orders 0/6 -> 1/3); N=3 CI very wide; never claim zero noise
- H3/H5 UNTESTED: grounded-v1 effect on negative-* and on ceiling tasks (find-/read-/symbol-)
- Task-prompt ambiguity ("Explain how an order total is computed" lacks "in this repo") not ruled out
  -> W4 D6: variant prompt, bump eval_version
- Baseline (N=6, earlier days) vs grounded (N=5, TPD-limited day) not same session
- Runner: llm_failed from 429/TPD counted as task failure -> add infra_failed, exclude from pass rate
- output_parse_failed 400 classified PERMANENT; retryability unmeasured
- Raw CoT may contain file content/secrets: scrub in trace (W7 D4)
- Reasoning items replayed every turn = input-token cost; consider pruning in W9
- Eval discriminating power low (10/12 tasks at ceiling/floor); add harder tasks before W5
- Reasoning shape verified on Groq gpt-oss-120b only
- RESOLVED: negative tasks 8/8 max_iterations ceiling under baseline/ledger/plan broken by no_progress nudge (threshold 2): completed 0/6 -> 5/6, token mean ~2.5k (-51%), one-sided Fisher p = 6/792 ≈ 0.0076 (N=12, negative tasks only)
- RESOLVED: refusal grader false-fail on real files mentioned by basename in refusal (Run 1 'orders.py' without src/); fixed via _is_real_path (rglob *.py); EVAL_VERSION bumped to 3
- RESOLVED: grader "50.00" false-fail (read-free-shipping 0% -> 100%)
- RESOLVED: unverified answer (explain-orders 0/3) fixed by grounded-v1 (5/5) and plan-on (3/3); trace confirmed orders.py read
- Thousands separators ("1,000") not handled by contains_word
- LoopGuard misses near-duplicate searches (different query strings)
- eval_version bump is manual
- RESOLVED: runner fixture isolation (temp workspace copy per run) & successful read tracking
- Eval system prompt differs from main.py (adds "say so if missing"); prompt must be versioned in reports (W4)
- N=3 gives wide confidence intervals; need N>=5 for trust
- Header-aware pacing (x-ratelimit-remaining-tokens) still open
- Latency in reports excludes cooldown but includes retry waits
- RESOLVED: decoy co-mention (forbidden), substring false-pass (word boundary)
- forbidden may false-fail correct explanations that mention the decoy
- 12 tasks × N repeats under TPM 8000 → runner needs rate-aware pacing (D5; use x-ratelimit headers)
- RESOLVED: Retry-After ticket (header path verified live: Groq returns `retry-after: 16` HTTP header; message path covered by tests)
- Proactive throttling from x-ratelimit-remaining/reset-tokens headers (avoid 429 entirely; ties into W9 context budget)
- Viewer llm_ms includes retry sleep; split wait vs model time (delay_s vs latency_ms)
- Error text in attempt_log contains org id (not secret); keep traces/ out of git
- Sleep is not remaining-wall-clock aware (should_abort is a bool, not remaining time)
- Message regex tied to Groq wording; trace has no schema_version
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
v0.7-pos-off 8/9; v0.7-pos-noprog2 8/9 (nudged 2). No full v4 baseline yet.

## Today's goal (next session)
Run v0.7 full baseline when console shows >= 150k, then W5 D1 (ACI design: tool output formatting,
truncation, pagination, glob tool).


