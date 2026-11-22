# ADR 0006: AI assistant is read-only in R1

Status: Superseded in part by ADR 0030 (2026-11-22: the assistant proposes actions, the user confirms them) · Date: 2026-11-17 · Phase 0

## Context
The assistant sends CRM content to an external LLM provider and processes untrusted text (notes, imports) that may contain prompt injection. Data flow approval is pending (requirements open question 1).

## Decision
In R1 the assistant has only read-only tools that call the service layer with the signed-in user's permissions. No tool creates, changes or deletes data. "Save as note" is an explicit user click using the normal activity endpoint. `AI_ENABLED` defaults to `false` until the owner confirms the data flow. Built in Phase 7.

## Consequences
Injected instructions cannot change data. Proposed actions with user confirmation are planned for R1.1 as a new ADR.
