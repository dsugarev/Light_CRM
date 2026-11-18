#!/usr/bin/env bash
# A second stack on the same host for the integrating teams (Conclusion, ERP, Billing)
# and for acceptance tests: separate data, keys and ports. Owner decision (Phase 8):
# no staging server; see docs/integration-readiness.md.
#
#   scripts/staging.sh init      create .env.staging (own secrets; ports 8080/8443)
#   scripts/staging.sh up        build and start, wait until ready
#   scripts/staging.sh seed EMAIL "FULL NAME"
#                                the first Admin (prints a set-password link), fictional
#                                demo data owned by them, and the three integration clients
#   scripts/staging.sh cli ...   run `python -m app.cli ...` in the staging backend
#   scripts/staging.sh down      stop (data kept)
#   scripts/staging.sh destroy   stop and delete the staging data
#
# Staging runs with ENV=test: API keys start with crm_test_, demo data is allowed,
# and it must never hold real customer data (CLAUDE.md, NFR-05).
set -euo pipefail
cd "$(dirname "$0")/.."

env_file=.env.staging
export COMPOSE_PROJECT_NAME=light-crm-staging
compose=(docker compose --env-file "$env_file")

need_env() { [[ -f "$env_file" ]] || { echo "Run: scripts/staging.sh init" >&2; exit 2; }; }

case "${1:-}" in
  init)
    [[ -f "$env_file" ]] && { echo "$env_file exists; delete it first to start over." >&2; exit 2; }
    gen() { openssl rand -hex 24; }
    sed -e "s/^ENV=.*/ENV=test/" \
        -e "s/^POSTGRES_PASSWORD=.*/POSTGRES_PASSWORD=$(gen)/" \
        -e "s/^CRM_MIGRATOR_PASSWORD=.*/CRM_MIGRATOR_PASSWORD=$(gen)/" \
        -e "s/^CRM_APP_PASSWORD=.*/CRM_APP_PASSWORD=$(gen)/" \
        -e "s/^APP_SECRET_KEY=.*/APP_SECRET_KEY=$(openssl rand -hex 32)/" \
        -e "s/^APP_ENCRYPTION_KEY=.*/APP_ENCRYPTION_KEY=$(openssl rand -hex 32)/" \
        -e "s/^CRM_HTTP_PORT=.*/CRM_HTTP_PORT=8080/" \
        -e "s/^CRM_HTTPS_PORT=.*/CRM_HTTPS_PORT=8443/" \
        -e "s#^CRM_BACKUP_DIR=.*#CRM_BACKUP_DIR=./backups-staging#" \
        -e "s#^CRM_PUBLIC_URL=.*#CRM_PUBLIC_URL=https://localhost:8443#" \
        .env.example > "$env_file"
    chmod 600 "$env_file"
    echo "Created $env_file. Set CRM_SITE_ADDRESS, CRM_PUBLIC_URL, CRM_TLS and"
    echo "WEBHOOK_ALLOWED_HOSTS for the teams' test systems, then: scripts/staging.sh up"
    ;;
  up)
    need_env
    "${compose[@]}" up --build --detach --wait
    port=$(grep -E '^CRM_HTTPS_PORT=' "$env_file" | cut -d= -f2)
    echo "Staging is running on port ${port:-8443}."
    ;;
  seed)
    need_env
    email="${2:?usage: scripts/staging.sh seed EMAIL \"FULL NAME\"}"
    name="${3:?usage: scripts/staging.sh seed EMAIL \"FULL NAME\"}"
    "${compose[@]}" exec -T backend python -m app.cli create-admin --email "$email" --full-name "$name"
    "${compose[@]}" exec -T backend python -m app.cli seed-demo
    "${compose[@]}" exec -T backend python -m app.cli create-integration-client --system all
    ;;
  cli)
    need_env
    shift
    "${compose[@]}" exec backend python -m app.cli "$@"
    ;;
  down)
    need_env
    "${compose[@]}" stop
    ;;
  destroy)
    need_env
    read -r -p "Delete ALL staging data? Type DELETE: " answer
    [[ "$answer" == "DELETE" ]] || { echo "Cancelled."; exit 1; }
    "${compose[@]}" down --volumes
    ;;
  *)
    sed -n '2,17p' "$0"
    exit 2
    ;;
esac
