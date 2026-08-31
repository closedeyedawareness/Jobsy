#!/usr/bin/env bash
# Apply the migration series to a throwaway database and attack it.
#
# The point is not that the DDL reads correctly — it is that the database
# refuses the writes it should refuse. Same standard PLAN-supabase-migration.md
# set for 0001: "verified by writing bad data and watching it bounce, not by
# reading the DDL back."
#
#   ./supabase/tests/run.sh                  # spins up its own Postgres
#   ./supabase/tests/run.sh "$DATABASE_URL"  # uses one you already have
#
# Never point this at a database you care about: it drops and recreates.
set -euo pipefail

cd "$(dirname "$0")/../.."
DB_NAME=jobsy_migration_test
OWN_SERVER=""

if [ $# -ge 1 ]; then
  PSQL_BASE=(psql "$1")
  ADMIN=("${PSQL_BASE[@]}")
else
  # No connection given: run a private Postgres in a temp dir and clean it up.
  PGBIN=$(ls -d /usr/lib/postgresql/*/bin 2>/dev/null | sort -V | tail -1 || true)
  [ -n "$PGBIN" ] || { echo "No local Postgres found. Pass a connection string instead."; exit 2; }
  RUNDIR=$(mktemp -d)
  OWN_SERVER=$RUNDIR
  chmod 711 "$RUNDIR"
  mkdir -p "$RUNDIR/data" "$RUNDIR/sock"
  # initdb refuses to run as root, so use the postgres account when we are it.
  AS_PG=""; [ "$(id -u)" = "0" ] && AS_PG="su postgres -c "
  if [ -n "$AS_PG" ]; then chown -R postgres "$RUNDIR"; fi
  ${AS_PG:+su postgres -c }"$PGBIN/initdb -D $RUNDIR/data -A trust -U postgres" >/dev/null
  ${AS_PG:+su postgres -c }"$PGBIN/pg_ctl -D $RUNDIR/data -o '-p 5433 -k $RUNDIR/sock -c listen_addresses=' -l $RUNDIR/pg.log start" >/dev/null
  trap '${AS_PG:+su postgres -c }"$PGBIN/pg_ctl -D $RUNDIR/data stop -m immediate" >/dev/null 2>&1 || true; rm -rf "$RUNDIR"' EXIT
  ADMIN=(psql -h "$RUNDIR/sock" -p 5433 -U postgres)
  PSQL_BASE=(psql -h "$RUNDIR/sock" -p 5433 -U postgres -d "$DB_NAME")
  "${ADMIN[@]}" -q -c "drop database if exists $DB_NAME;" -c "create database $DB_NAME;"
fi

RUN=("${PSQL_BASE[@]}" -q -v ON_ERROR_STOP=1)

# Only when we own the server: plain Postgres has no auth schema or Supabase
# roles, and the migrations reference both. Never applied to a real project.
if [ -n "$OWN_SERVER" ]; then
  "${RUN[@]}" -f supabase/tests/_supabase_stub.sql
fi

for f in supabase/migrations/*.sql; do
  printf '  %-48s ' "$(basename "$f")"
  if "${RUN[@]}" -f "$f" >/dev/null 2>&1; then echo "applied"; else echo "FAILED"; "${RUN[@]}" -f "$f"; exit 1; fi
done

echo
OUT=$("${PSQL_BASE[@]}" -f supabase/tests/0007_tenancy_test.sql 2>&1 | grep -Ev '^$|^INSERT|^CREATE|^SET|^RESET|^Output format')
echo "$OUT"
echo

FAILED=$(printf '%s\n' "$OUT" | grep -c '^FAIL' || true)
PASSED=$(printf '%s\n' "$OUT" | grep -c '^ok' || true)
echo "$PASSED passed, $FAILED failed"
[ "$FAILED" -eq 0 ] || exit 1
