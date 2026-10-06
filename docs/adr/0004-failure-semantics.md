# ADR-0004: Failure semantics

## Status
Accepted

## Principle
A model's bad output or a tool's failure is an observation, not a run failure.
A run ends only on a runtime guard or an unrecoverable provider failure.

## Table
| Fault | Caught by | Outcome | Model sees it |
|---|---|---|---|
| Malformed tool args (bad JSON / not an object) | `parse_tool_call` | continue | yes |
| Wrong arg types / unknown field | `ToolExecutor` validation | continue | yes |
| Tool exception | `ToolExecutor` boundary | continue | yes |
| N consecutive malformed calls | loop counter | `LOOP_DETECTED` | last one only |
| Same call repeated (Nth) | `LoopGuard` | `LOOP_DETECTED` | no |
| Timeout / 5xx / connection / 429 | `ResilientClient` | retry, then `LLM_FAILED` | no |
| 4xx permanent, unknown error | classifier | `LLM_FAILED` | no |
| Deadline during retry | `should_abort` | `TIMEOUT` | no |
| Wall-clock / iteration budget | loop | `TIMEOUT` / `MAX_ITERATIONS` | no |
| Token budget exceeded with tool calls | loop | `TOKEN_BUDGET_EXCEEDED`, tools not run | no |
| Missing usage with budget set | `UsageTracker` | `TOKEN_BUDGET_EXCEEDED` (fail closed) | no |
| Empty final answer | loop | `LLM_FAILED` | no |

Final answers are accepted even when over the token budget.

## Known limits
- Retries use exponential backoff without jitter and ignore `Retry-After`.
  A live 429/TPM event showed this matters; implement `Retry-After` before
  multi-agent work.
- Usage of failed attempts is not observable, so cost reports are a lower bound.
- A budget stop leaves a dangling `function_call` in the conversation; relevant
  for resume (W12).
- `.env` is readable via `read_file` (W7 D4).
