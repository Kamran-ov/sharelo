#!/usr/bin/env bash
# Starts PostgreSQL as a local process for sessions without a Docker daemon and creates the
# sharelo role and database. Run it (./scripts/cloud-setup.sh); it also works if sourced.
# The Makefile defaults DATABASE_URL to the same value, so the export below is a convenience.
DB_URL="postgres://sharelo:sharelo@localhost:5432/sharelo"

setup_postgres() {
set -eu
if ! command -v pg_ctlcluster >/dev/null 2>&1; then
  apt-get update -qq
  apt-get install -y -qq postgresql postgresql-client
fi

VERSION="$(ls /usr/lib/postgresql | sort -n | tail -n 1)"
if ! pg_lsclusters -h | grep -q "^${VERSION} main .* online"; then
  pg_ctlcluster "$VERSION" main start
fi
pg_isready -q -h localhost -p 5432 -t 30

as_postgres() { su postgres -c "$1"; }
as_postgres "psql -qtAc \"SELECT 1 FROM pg_roles WHERE rolname='sharelo'\"" | grep -q 1 ||
  as_postgres "psql -qc \"CREATE ROLE sharelo LOGIN SUPERUSER PASSWORD 'sharelo'\""
as_postgres "psql -qtAc \"SELECT 1 FROM pg_database WHERE datname='sharelo'\"" | grep -q 1 ||
  as_postgres "createdb -O sharelo sharelo"
}

# subshell, so a sourcing shell does not inherit set -e
(setup_postgres) || return 1 2>/dev/null || exit 1

export DATABASE_URL="$DB_URL"
echo "PostgreSQL ready. DATABASE_URL=$DATABASE_URL"
