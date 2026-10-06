# Agent Runtime

A coding agent runtime built from scratch in Python.

## Goals

This project implements a software engineering agent without:

- LangChain
- LangGraph
- CrewAI
- LlamaIndex

Only an LLM provider SDK is used for model communication.

## Current Provider

OpenAI (Groq-compatible Responses API)

## Architecture

```text
Agent Runtime (app/agent)
     |
     v
 LLMClient Protocol (app/llm)
     |
     +---- OpenAIClient
     |
     +---- FakeLLMClient
```

## Layout
- `app/tools`: tool abstraction, workspace boundary, validation (imports nothing else in app)
- `app/llm`: provider-neutral LLMClient, OpenAI adapter, retry, errors
- `app/agent`: loop, state, budgets, guards, cost (never imports a provider SDK)

## Verify
```bash
pytest -q            # production suite
python -m app.main   # live run (needs OPENAI_API_KEY, Groq)
```

## Design records
- `docs/adr/0001..0004`