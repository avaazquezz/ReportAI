#!/usr/bin/env bash
# Restores a backup made by backup.sh into the running stack. DESTRUCTIVE: it drops and
# recreates the database, and overwrites the storage volume's files.
#
#   infra/restore.sh --yes /var/backups/reportai/db-<stamp>.sql.gz [/var/backups/reportai/storage-<stamp>.tar.gz]
#
# Stop the API first (`docker compose -f infra/docker-compose.prod.yml stop backend`) so it
# isn't holding connections, and start it again afterwards. Rehearse this against a scratch
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

gzip -t "$db_file"
[ -z "$storage_file" ] || tar -tzf "$storage_file" > /dev/null

docker exec "$PG_CONTAINER" sh -c '
  psql -U "$POSTGRES_USER" -d postgres -v ON_ERROR_STOP=1 \
    -c "DROP DATABASE IF EXISTS \"$POSTGRES_DB\" WITH (FORCE)" \
    -c "CREATE DATABASE \"$POSTGRES_DB\""'
zcat "$db_file" | docker exec -i "$PG_CONTAINER" sh -c 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -v ON_ERROR_STOP=1 -q' > /dev/null

if [ -n "$storage_file" ]; then
  docker run --rm -i -v "$STORAGE_VOLUME":/data alpine sh -c 'cd /data && tar xzf -' < "$storage_file"
fi

echo "restore ok from $(basename "$db_file")"
