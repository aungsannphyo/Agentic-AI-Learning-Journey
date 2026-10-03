## Current

Week 2 / Day 2 — Pydantic Validation
Date: 2026-10-03

## Done

### Week 2 Day 1
- Machine-verifiable Decision schema
- DecisionAction enum
- Structured output strategies comparison
- Prompt-based JSON parsing
- Provider-agnostic structured payload validation
- JSON Schema generation

### Week 2 Day 2
- Added ToolArgs base Pydantic model
- Added ListFilesArgs
- Added ReadFileArgs
- Added SearchTextArgs
- Added strict unknown-field rejection
- Added field-level constraints
- Added ToolArgumentRegistry
- Added tool-name → argument-schema mapping
- Added structured validation error formatter
- Distinguished schema validation from workspace authorization
- Added validation tests for invalid types, missing fields, invalid ranges, and unknown fields

## Key Design Decisions

- `Decision` validates agent-level intent
- `ToolArgs` validates tool-level input contracts
- `ToolArgumentRegistry` maps tool names to their argument schemas
- Pydantic validation happens before tool execution
- Validation errors are converted into structured observations
- Workspace remains responsible for path authorization/security
- Schema validation and execution security remain separate boundaries

## Code State

agent-runtime/
├── app/
│   ├── agent/
│   │   ├── decision.py
│   │   ├── decision_schema.py
│   │   ├── structured_output.py
│   │   └── validation_errors.py
│   └── tools/
│       ├── argument_registry.py
│       └── schemas.py
└── tests/
    ├── test_decision.py
    ├── test_structured_output.py
    ├── test_tool_schemas.py
    ├── test_argument_registry.py
    └── test_validation_errors.py

## Today's Goal

Create a typed Pydantic validation layer for tool arguments
and convert validation failures into structured agent observations.

## Next

Week 2 / Day 3 — Malformed Output + Retry
- Error feedback to LLM
- Bounded retry
- Exponential backoff
- Transient vs permanent errors
- Error taxonomy