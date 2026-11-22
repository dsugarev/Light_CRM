#!/usr/bin/env bash
# Builds the PDF versions of the user manuals in docs/manual from their Markdown.
# Needs pandoc (3.x) and the frontend's Playwright Chromium (`pnpm exec playwright install chromium`).
set -euo pipefail

root="$(cd "$(dirname "$0")/.." && pwd)"
manual="$root/docs/manual"
build="$(mktemp -d)"
trap 'rm -rf "$build"' EXIT
mkdir -p "$manual/pdf"

for role in sales-rep sales-manager admin viewer; do
  title="$(head -n 1 "$manual/$role.md" | sed 's/^# //')"
  # GitHub-flavoured Markdown, so heading anchors match the links on GitHub;
  # images and the stylesheet are embedded so the HTML is self-contained.
  pandoc "$manual/$role.md" \
    --from gfm --to html5 --standalone --embed-resources \
    --resource-path "$manual" \
    --css "$manual/manual.css" \
    --metadata pagetitle="$title" \
    --output "$build/$role.html"
  (cd "$root/frontend" && node scripts/manual-pdf.mjs "$build/$role.html" \
    "$manual/pdf/light-crm-manual-$role.pdf" "$title")
done
