# ADR 0002: FastAPI and React stack

Status: Accepted · Date: 2026-11-17 · Phase 0

## Context
Architecture section 2 fixes the stack; exact versions are chosen at implementation time (current stable / LTS) and pinned.

## Decision
- Backend: Python 3.14, FastAPI, Pydantic v2, SQLAlchemy 2 (async, asyncpg), Alembic, uv, Ruff, mypy (strict), pytest, import-linter, pip-audit. `pydantic-settings` for environment configuration.
- Frontend: Node 26 LTS, pnpm, Vite, React 19, TypeScript 6.0 (strict), React Router, TanStack Query, Tailwind CSS 4, shadcn/ui, i18next, openapi-typescript + openapi-fetch, ESLint (typescript-eslint, eslint-plugin-i18next), Prettier, Vitest, Testing Library, MSW, Playwright.
- All versions pinned exactly (`pyproject.toml` + `uv.lock`, `package.json` + `pnpm-lock.yaml`; Docker images by full tag; GitHub Actions by commit SHA).

## Notes on specific choices
- **TypeScript 6.0, not 7.x:** typescript-eslint supports TypeScript < 6.1. Move to 7.x when typed linting supports it.
- **shadcn/ui** now generates components on Base UI (`@base-ui/react`) with the `cn` helper package from the shadcn maintainers, Geist font self-hosted via Fontsource (no external requests, CSP-compatible).
- **openapi-fetch** is a thin typed wrapper over the generated types; it is the only HTTP client in the SPA.
- Python 3.14 provides `uuid.uuid7()` in the standard library for UUIDv7 primary keys (architecture 4.1).

## Consequences
Upgrades are deliberate changes to lockfiles, reviewed like code.
