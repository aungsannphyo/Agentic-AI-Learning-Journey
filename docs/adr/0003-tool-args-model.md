# ADR-0003: Tool.args_model is the single source of truth

## Status
Accepted

## Context
Three places described a tool's input: a hand-written JSON schema shown to the
model, a registry of Pydantic validators, and constructor limits actually used.
They drifted: `max_bytes` was accepted by validation but ignored by the tool.

## Decision
- Each tool declares one Pydantic `args_model`. The model-facing strict JSON
  schema is derived from it (`strict_json_schema`); runtime validation uses it.
- Validation in `ToolExecutor` is mandatory (no bypass path).
- Budget/safety limits (`max_bytes`, `max_results`, `max_file_bytes`) are tool
  configuration, never model-facing.
- Malformed tool-call JSON becomes `ToolCall.parse_error` and an observation,
  not a run failure. Consecutive malformed calls are capped.

## Consequences
- Adding a tool means editing one place; `tests/test_schema_derivation.py`
  checks strict-schema invariants for every tool.
- The model cannot raise its own limits. Consequence: it reads whole files and
  slices them itself (observed). Model-facing `offset`/`limit` is planned for W5.
- `Tool.run` still takes a raw dict; typed args are deferred to W5.
- `strict_json_schema` does not support nested models; strict-mode acceptance
  was verified by live run against Groq only.
