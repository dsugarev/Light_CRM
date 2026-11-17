#!/usr/bin/env bash
# Shared by start-mac.sh and start-linux.sh: start the production-like stack.
set -euo pipefail
cd "$(dirname "$0")/.."

command -v docker >/dev/null 2>&1 || { echo "Docker is required: https://docs.docker.com/get-docker/" >&2; exit 1; }

if [[ ! -f .env ]]; then
  gen() { openssl rand -hex 24; }
  sed -e "s/^POSTGRES_PASSWORD=.*/POSTGRES_PASSWORD=$(gen)/" \
      -e "s/^CRM_MIGRATOR_PASSWORD=.*/CRM_MIGRATOR_PASSWORD=$(gen)/" \
      -e "s/^CRM_APP_PASSWORD=.*/CRM_APP_PASSWORD=$(gen)/" \
      -e "s/^APP_SECRET_KEY=.*/APP_SECRET_KEY=$(openssl rand -hex 32)/" \
      .env.example > .env
  chmod 600 .env
  echo "Created .env with generated passwords and secret key."
fi
# Settings added in later releases: append generated values to an existing .env.
if ! grep -q '^APP_SECRET_KEY=' .env; then
  printf '\n# Added by start script\nAPP_SECRET_KEY=%s\n' "$(openssl rand -hex 32)" >> .env
  echo "Added APP_SECRET_KEY to .env."
fi

docker compose up --build --detach

port=$(grep -E '^CRM_HTTPS_PORT=' .env | cut -d= -f2); port=${port:-443}
host=$(grep -E '^CRM_SITE_ADDRESS=' .env | cut -d= -f2); host=${host:-localhost}
url="https://${host}$([[ "$port" == 443 ]] || echo ":$port")"

echo "Waiting for the CRM to become ready..."
for _ in $(seq 1 90); do
  if curl --silent --fail --insecure "$url/api/health/ready" >/dev/null 2>&1; then
    echo "CRM is running at $url"
    exit 0
  fi
  sleep 2
done
echo "The CRM did not become ready in time. Check: docker compose logs" >&2
exit 1
