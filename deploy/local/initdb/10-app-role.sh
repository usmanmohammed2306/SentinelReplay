#!/bin/sh
set -eu

# Runs only when the disposable/local PostgreSQL volume is initialized.
# The migrator grants table privileges after it creates the schema.
psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" \
  -v app_password="$SENTINEL_APP_DB_PASSWORD" <<'SQL'
CREATE ROLE sentinel_api LOGIN PASSWORD :'app_password';
GRANT CONNECT ON DATABASE sentinel TO sentinel_api;
GRANT USAGE ON SCHEMA public TO sentinel_api;
SQL
