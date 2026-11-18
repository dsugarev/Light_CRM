# ADR 0022: Ignoring one development-only advisory in the CI audit

Status: Accepted (temporary) · Date: 2026-11-17 · Phase 5a

## Context
CI runs `pnpm audit --audit-level high` over all frontend dependencies. On 2026-11-17 advisory GHSA-fc5q-39xc-vjpf (picomatch ReDoS through single-branch repeated extglobs, high) was published with no patched version. picomatch reaches the project only through development tooling (shadcn CLI, Vite, ESLint, Vitest globbing over our own source patterns); `pnpm audit --prod` is clean. Every pull request, including `main`, failed the gate.

## Decision
Owner decision (2026-11-17): ignore exactly this advisory through `auditConfig.ignoreGhsas` in `frontend/pnpm-workspace.yaml`, with a comment pointing here. All other advisories, of any dependency, still fail CI at high severity. The production audit (`pnpm audit --prod`) stays part of the local gate.

## Consequences
- CI is green again without lowering the threshold or narrowing the audit scope.
- The entry must be removed as soon as picomatch publishes a fix (tracked as an open item in `Plan.md`); `pnpm audit` reports the ignored advisory on every run as a reminder.
