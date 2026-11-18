# UI polish loop — progress log

Note: the backlog was written after Phase 1; the application is now at v1.0.0, so several items may already be partly or fully met. Each entry says what was found.

## UX-01 — 2026-11-18 13:40

- **What changed:** every remaining color literal and Tailwind palette color moved to theme tokens in `frontend/src/index.css`. New tokens (light and dark): `--brand` (with `TODO(owner): brand color`; `--primary` now points to it), `--destructive-foreground`, `--success`, `--overlay`, `--qr-surface` (QR codes need a white quiet zone in both themes). Radii and spacing already came from `--radius` and Tailwind's `--spacing`.
- **Replaced:** the API status dot (`bg-emerald-500`/`bg-red-500` → `bg-success`/`bg-destructive`), the won drop zone on the board (`border-success/60`), the MFA QR background (`bg-qr-surface`), the alert-dialog backdrop (`bg-overlay/10`), the failing-deliveries badge text (`text-destructive-foreground`), and the dashboard chart fills (hex fallbacks removed).
- **Files:** `frontend/src/index.css`, `src/app/AppLayout.tsx`, `src/components/ui/alert-dialog.tsx`, `src/features/system/ApiStatus.tsx`, `src/features/profile/MfaCard.tsx`, `src/features/opportunities/BoardPage.tsx`, `src/features/reports/Dashboard.tsx`.
- **Tests:** `src/app/designTokens.test.ts`, which scans every source file except tests and the generated schema and fails on any hex/rgb/hsl/oklch literal or Tailwind palette color (`UX-01 ...`). A file with a planted `#fff bg-red-500` was confirmed to fail it.
- **Looked at:** dashboard, board and profile in en/bg at 1440 and 768 px; no visual change apart from the slightly different red and green of the status dot. Axe (`e2e/accessibility.spec.ts`, Chromium): passed.
- **Gate:** frontend lint, prettier, typecheck, Vitest 147/147, i18n 1065 keys; backend ruff, format, mypy, import-linter 14/14, pytest 1303 passed (95.56%). No backend or API change, so the generated types are unchanged.
- **For later:** clipped Y-axis labels and the weak "Weighted" chart contrast on the dashboard were already there before this change; logged as C-07.
