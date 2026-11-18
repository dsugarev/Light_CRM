#!/usr/bin/env bash
# Nightly PostgreSQL backup (NFR-07): custom-format pg_dump at BACKUP_TIME
# (container local time, default 02:00), files older than BACKUP_RETENTION_DAYS
# (default 10; copies on another machine keep longer) are deleted. Connection settings come from PGHOST, PGUSER,
# PGPASSWORD and PGDATABASE. The restore procedure is documented and drilled
# in Phase 8.
set -euo pipefail

BACKUP_DIR="${BACKUP_DIR:-/backups}"
BACKUP_TIME="${BACKUP_TIME:-02:00}"
RETENTION_DAYS="${BACKUP_RETENTION_DAYS:-10}"

backup_once() {
  local file="$BACKUP_DIR/crm-$(date -u +%Y%m%dT%H%M%SZ).dump"
  echo "backup: writing $file"
  pg_dump --format=custom --file="$file.partial"
  mv "$file.partial" "$file"
  find "$BACKUP_DIR" -name 'crm-*.dump' -type f -mtime "+$RETENTION_DAYS" -print -delete
}

if [[ "${1:-}" == "--now" ]]; then
  backup_once
  exit 0
fi

while true; do
  now=$(date +%s)
  next=$(date -d "today $BACKUP_TIME" +%s)
  (( next <= now )) && next=$(date -d "tomorrow $BACKUP_TIME" +%s)
  echo "backup: next run at $(date -d "@$next")"
  sleep $(( next - now ))
  backup_once || echo "backup: FAILED" >&2
done
