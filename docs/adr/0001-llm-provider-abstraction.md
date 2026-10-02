# ADR-0001: Introduce a Provider-Independent LLM Interface

## Status

Accepted

## Context

The coding agent needs to communicate with an LLM provider.

The initial provider is OpenAI.

However, coupling the agent runtime directly to the OpenAI SDK would
make the core runtime dependent on a specific provider.

The project also needs deterministic tests that do not make real
network calls or consume API credits.

## Decision

Introduce a provider-independent `LLMClient` interface.

The runtime depends on:

    LLMClient

The OpenAI implementation is:

    OpenAIClient

Tests can use:

    FakeLLMClient

The OpenAI SDK is therefore isolated behind the LLM client boundary.

## Consequences

### Positive

- Agent runtime is not coupled directly to OpenAI.
- Tests can be deterministic.
- Provider replacement is easier.
- External API concerns remain isolated.
- Future tool-calling implementation can map provider-specific
  responses into internal runtime models.

### Negative

- Adds a small abstraction layer.
- Provider-specific capabilities may require additional interfaces
  or adapters later.

## Alternatives Considered

### Direct OpenAI SDK usage

Rejected because it couples the runtime to a specific provider.

### Generic third-party agent framework

Rejected because this project explicitly builds the runtime
from scratch for learning and architectural understanding.