# ADR-0002: Provider-neutral LLM interface

## Status
Accepted (supersedes the interface part of ADR-0001)

## Context
The loop originally depended on the OpenAI Responses API shape
(`response.output`, `function_call_output`) and on SDK objects stored
directly in the conversation. That broke the provider-independence goal of
ADR-0001, made the conversation non-serializable, and forced retry/deadline
state onto a shared client object.

## Decision
1. `LLMClient` is a single `Protocol` with one method:
   `complete(messages, tools, should_abort) -> LLMResponse`.
2. `LLMResponse(text, tool_calls, usage, assistant_items, attempts)` is a frozen,
   internal type. `assistant_items` are opaque JSON-serializable provider items
   that the same provider must receive back on the next call.
3. The conversation is a provider-neutral list of JSON dicts
   (`user`, `assistant`, `tool_result`). Provider format conversion happens only
   inside the client adapter.
4. The run deadline is a call parameter (`should_abort`). `ResilientClient` is
   stateless; attempt history travels on the response or the raised exception.
5. Layering: `app/agent` must not import `openai`; `app/llm` must not import
   `app/agent`; `app/tools` imports neither. Enforced by `tests/test_layering.py`.

## Evidence (measured on Groq, openai/gpt-oss-120b)
- Replaying `model_dump(mode="json", exclude_none=True)` reasoning and
  function_call items on the next turn is accepted (no 400).
- `total_tokens = input_tokens + output_tokens`; `reasoning_tokens` is already
  included in `output_tokens`. Cost = input*price_in + output*price_out is
  therefore reasoning-inclusive (an estimate, not billing-grade).
- `max_output_tokens` is supported and is a hard cap, but it also caps
  reasoning: at 50 tokens, 48 were spent on reasoning and no message or tool call
  was produced (`status=incomplete`).

## Consequences
- Positive: provider swap touches only an adapter; conversation is
  serializable (trace/resume); retry layer is safe to share.
- Negative: replay correctness is verified on one provider and a few runs.
  An empty final answer is treated as `LLM_FAILED`, not `COMPLETED`.
- Not done: `max_output_tokens` is not set (needs a measured reasoning-token
  distribution first); `LLMResponse` has no `incomplete_reason`.
