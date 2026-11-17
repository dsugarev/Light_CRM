#!/usr/bin/env bash
# Creates the two database roles (architecture section 7, "Database"):
#   crm_migrator  owns the database and schema; runs Alembic migrations (DDL)
#   crm_app       used by the backend and worker; data access only (DML)
# Tables created by crm_migrator are granted to crm_app automatically through
# default privileges. Later migrations narrow them where needed (for example,
# audit_log is INSERT/SELECT only for crm_app).
#
# Runs automatically on first start of the Postgres container (mounted into
# /docker-entrypoint-initdb.d) and can be re-run safely, e.g. in CI:
#   PGHOST=localhost PGPASSWORD=... POSTGRES_USER=postgres ./init-roles.sh
#
# Environment:
#   POSTGRES_USER            superuser to connect as (default: postgres)
#   CRM_DB_NAME              main database (default: crm)
#   CRM_EXTRA_DATABASES      space-separated extra databases, e.g. "crm_test"
#   CRM_MIGRATOR_PASSWORD    password for crm_migrator (required)
#   CRM_APP_PASSWORD         password for crm_app (required)
set -euo pipefail

: "${CRM_MIGRATOR_PASSWORD:?CRM_MIGRATOR_PASSWORD is required}"
: "${CRM_APP_PASSWORD:?CRM_APP_PASSWORD is required}"
SUPERUSER="${POSTGRES_USER:-postgres}"
MAIN_DB="${CRM_DB_NAME:-crm}"

psql_super() {
  psql -v ON_ERROR_STOP=1 --username "$SUPERUSER" --no-password "$@"
}

psql_super --dbname postgres \
  -v migrator_password="$CRM_MIGRATOR_PASSWORD" \
  -v app_password="$CRM_APP_PASSWORD" <<'SQL'
SELECT format('CREATE ROLE crm_migrator LOGIN PASSWORD %L', :'migrator_password')
WHERE NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'crm_migrator') \gexec
SELECT format('ALTER ROLE crm_migrator LOGIN PASSWORD %L', :'migrator_password') \gexec
SELECT format('CREATE ROLE crm_app LOGIN PASSWORD %L', :'app_password')
WHERE NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'crm_app') \gexec
SELECT format('ALTER ROLE crm_app LOGIN PASSWORD %L', :'app_password') \gexec
SQL

for db in $MAIN_DB ${CRM_EXTRA_DATABASES:-}; do
  psql_super --dbname postgres -v db="$db" <<'SQL'
SELECT format('CREATE DATABASE %I OWNER crm_migrator ENCODING ''UTF8'' TEMPLATE template0', :'db')
WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = :'db') \gexec
SELECT format('ALTER DATABASE %I OWNER TO crm_migrator', :'db') \gexec
SELECT format('REVOKE ALL ON DATABASE %I FROM PUBLIC', :'db') \gexec
SELECT format('GRANT CONNECT, TEMPORARY ON DATABASE %I TO crm_app', :'db') \gexec
SQL

  psql_super --dbname "$db" <<'SQL'
ALTER SCHEMA public OWNER TO crm_migrator;
REVOKE ALL ON SCHEMA public FROM PUBLIC;
GRANT USAGE ON SCHEMA public TO crm_app;
ALTER DEFAULT PRIVILEGES FOR ROLE crm_migrator IN SCHEMA public
  GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO crm_app;
ALTER DEFAULT PRIVILEGES FOR ROLE crm_migrator IN SCHEMA public
  GRANT USAGE, SELECT ON SEQUENCES TO crm_app;
ALTER DEFAULT PRIVILEGES FOR ROLE crm_migrator IN SCHEMA public
  GRANT EXECUTE ON FUNCTIONS TO crm_app;
SQL
done

echo "init-roles: roles crm_migrator and crm_app ready for: $MAIN_DB ${CRM_EXTRA_DATABASES:-}"
