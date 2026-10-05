# Week 2 D1: Structured-output experiments

Comparison of three ways to get a machine-verifiable decision from an LLM
(prompt-based JSON, provider-constrained output, tool-call-as-schema).

NOT part of the runtime. The agent loop uses native tool calling, which
already provides the tool_call / final_answer split. Kept as a learning
artifact; run with `pytest experiments`.
