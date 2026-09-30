#!/usr/bin/env bash
# Restores a backup made by backup.sh into the running stack. DESTRUCTIVE: it drops and
# recreates the database, and overwrites the storage volume's files.
#
#   infra/restore.sh --yes /var/backups/reportai/db-<stamp>.sql.gz [/var/backups/reportai/storage-<stamp>.tar.gz]
#
# Stop the API first (`docker compose -f infra/docker-compose.prod.yml stop backend`) so it
# isn't holding connections, and start it again afterwards (not needed with TARGET_DB). Rehearse this against a scratch
# server before you need it — an untested backup is a hope, not a backup.
set -euo pipefail

if [ "${1:-}" != "--yes" ]; then
  echo "This replaces the live database (and storage files). Re-run with --yes as the first argument." >&2
  exit 1
fi
shift
db_file=${1:?usage: restore.sh --yes <db-backup.sql.gz> [storage-backup.tar.gz]}
storage_file=${2:-}

PG_CONTAINER=${PG_CONTAINER:-reportai_postgres}
STORAGE_VOLUME=${STORAGE_VOLUME:-reportai_storage_data}
# Restore into another database to rehearse without touching the live one:
#   TARGET_DB=restore_test infra/restore.sh --yes <db-backup>
TARGET_DB=${TARGET_DB:-}

gzip -t "$db_file"
[ -z "$storage_file" ] || tar -tzf "$storage_file" > /dev/null

docker exec -e TARGET_DB="$TARGET_DB" "$PG_CONTAINER" sh -c '
  db=${TARGET_DB:-$POSTGRES_DB}
  psql -U "$POSTGRES_USER" -d postgres -v ON_ERROR_STOP=1 \
    -c "DROP DATABASE IF EXISTS \"$db\" WITH (FORCE)" \
    -c "CREATE DATABASE \"$db\""'
zcat "$db_file" | docker exec -i -e TARGET_DB="$TARGET_DB" "$PG_CONTAINER" sh -c 'psql -U "$POSTGRES_USER" -d "${TARGET_DB:-$POSTGRES_DB}" -v ON_ERROR_STOP=1 -q' > /dev/null

if [ -n "$storage_file" ]; then
  docker run --rm -i -v "$STORAGE_VOLUME":/data alpine sh -c 'cd /data && tar xzf -' < "$storage_file"
fi

echo "restore ok from $(basename "$db_file")"
