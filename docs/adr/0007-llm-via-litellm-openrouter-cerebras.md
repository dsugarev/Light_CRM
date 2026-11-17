# ADR 0007: LLM access via LiteLLM, OpenRouter and Cerebras

Status: Accepted · Date: 2026-11-17 · Phase 0

## Context
Mandated by the owner: LiteLLM → OpenRouter → model `openrouter/openai/gpt-oss-120b` with Cerebras as the inference provider (project Cerebras skill).

## Decision
`backend/app/llm/client.py` is the only module that imports `litellm`, enforced by an import-linter contract. It uses the async call with the skill's parameters (`extra_body={"provider": {"order": ["cerebras"]}}`, `reasoning_effort="low"`). Configuration from environment (`OPENROUTER_API_KEY`, `LLM_MODEL`, timeouts, budgets). Tests inject a fake client; CI never calls the live model. Built in Phase 7.

## Consequences
The model and provider can be swapped in one file; nothing else in the application depends on the LLM.
