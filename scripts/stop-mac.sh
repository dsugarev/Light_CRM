#!/usr/bin/env bash
# Stop the CRM. Data (database volume, backups) is kept.
set -euo pipefail
cd "$(dirname "$0")/.."
docker compose down
