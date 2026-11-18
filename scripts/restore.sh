#!/usr/bin/env bash
# Restore a nightly backup into a Compose stack (NFR-07; docs/operations-guide.md).
#
#   scripts/restore.sh backups/crm-20261118T010912Z.dump          # the main stack
#   CRM_ENV_FILE=.env.drill COMPOSE_PROJECT_NAME=light-crm-drill \
#     scripts/restore.sh backups/crm-20261118T010912Z.dump        # a second stack
#
# DESTRUCTIVE: the stack's `crm` database is replaced by the backup. Asks you to
# type RESTORE unless --yes is given. Steps: stop the application services, recreate
# the database with its roles and grants (deploy/postgres/init-roles.sh), restore the
# dump as its owner (crm_migrator), start the stack again (pending migrations run, so
# an older backup is brought up to the current schema), and wait until it is ready.
set -euo pipefail
cd "$(dirname "$0")/.."

dump="${1:-}"
assume_yes="${2:-}"
if [[ -z "$dump" || ! -f "$dump" ]]; then
  echo "usage: scripts/restore.sh <backup.dump> [--yes]" >&2
  exit 2
fi
env_file="${CRM_ENV_FILE:-.env}"
[[ -f "$env_file" ]] || { echo "No $env_file: the stack is not configured" >&2; exit 2; }
compose=(docker compose --env-file "$env_file")
project="${COMPOSE_PROJECT_NAME:-light-crm}"

if [[ "$assume_yes" != "--yes" ]]; then
  echo "This replaces ALL data of the stack '$project' with $dump."
  read -r -p "Type RESTORE to continue: " answer
  [[ "$answer" == "RESTORE" ]] || { echo "Cancelled."; exit 1; }
fi

# The database role passwords come from the stack's configuration.
migrator_password=$(grep -E '^CRM_MIGRATOR_PASSWORD=' "$env_file" | cut -d= -f2-)
app_password=$(grep -E '^CRM_APP_PASSWORD=' "$env_file" | cut -d= -f2-)

started=$(date +%s)
step() { echo "[$(( $(date +%s) - started ))s] $*"; }
trap 'echo "Restore FAILED. See: docker compose --env-file $env_file logs" >&2' ERR

step "Stopping the application services"
"${compose[@]}" stop backend worker proxy backup >/dev/null 2>&1 || true
step "Starting the database"
"${compose[@]}" up --detach --wait db >/dev/null 2>&1

step "Recreating the database with its roles and grants"
"${compose[@]}" exec -T db psql -v ON_ERROR_STOP=1 -U postgres -d postgres -q \
  -c "DROP DATABASE IF EXISTS crm WITH (FORCE)"
"${compose[@]}" exec -T \
  -e CRM_MIGRATOR_PASSWORD="$migrator_password" -e CRM_APP_PASSWORD="$app_password" \
  db bash /docker-entrypoint-initdb.d/10-init-roles.sh >/dev/null

step "Restoring $dump"
"${compose[@]}" exec -T db pg_restore --exit-on-error --no-owner -U crm_migrator -d crm < "$dump"

step "Starting the stack (pending migrations run first)"
"${compose[@]}" up --detach --wait >/dev/null 2>&1
step "Restored and ready."
