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

OpenAI

## Architecture

```text
Agent Runtime
     |
     v
 LLMClient
     |
     +---- OpenAIClient
     |
     +---- FakeLLMClient