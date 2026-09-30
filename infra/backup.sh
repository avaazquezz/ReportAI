#!/usr/bin/env bash
# Backs up the two things that can't be regenerated: the Postgres database and the storage
# volume (customers' .docx templates and generated PDFs live there). Run it nightly from cron
# on the host that runs the prod compose:
#
#   30 4 * * * /path/to/ReportAI/infra/backup.sh >> /var/log/reportai-backup.log 2>&1
#
# A backup that stays on the same disk as the data it protects is not a backup: set
# BACKUP_SYNC_CMD to copy BACKUP_DIR somewhere else (see infra/README.md), and
# BACKUP_PING_URL to a dead-man's-switch monitor so a night that silently didn't run alerts you.
set -euo pipefail

PG_CONTAINER=${PG_CONTAINER:-reportai_postgres}
STORAGE_VOLUME=${STORAGE_VOLUME:-reportai_storage_data}
BACKUP_DIR=${BACKUP_DIR:-/var/backups/reportai}
KEEP_DAYS=${KEEP_DAYS:-14}
BACKUP_SYNC_CMD=${BACKUP_SYNC_CMD:-}
BACKUP_PING_URL=${BACKUP_PING_URL:-}

stamp=$(date -u +%Y%m%dT%H%M%SZ)
db_file="$BACKUP_DIR/db-$stamp.sql.gz"
storage_file="$BACKUP_DIR/storage-$stamp.tar.gz"
mkdir -p "$BACKUP_DIR"
trap 'rm -f "$db_file.partial" "$storage_file.partial"' EXIT

# Written under a .partial name and renamed only after it verifies, so a failed run never
# leaves something that looks like a good backup. pipefail (above) makes a failing pg_dump
# fail the whole pipeline — without it, `pg_dump | gzip` exits 0 with an empty archive.
docker exec "$PG_CONTAINER" sh -c 'pg_dump -U "$POSTGRES_USER" "$POSTGRES_DB"' | gzip > "$db_file.partial"
gzip -t "$db_file.partial"
# pg_dump writes this footer only when it reached the end of the dump.
zcat "$db_file.partial" | tail -n 5 | grep -q 'PostgreSQL database dump complete'
mv "$db_file.partial" "$db_file"

docker run --rm -v "$STORAGE_VOLUME":/data:ro alpine tar czf - -C /data . > "$storage_file.partial"
tar -tzf "$storage_file.partial" > /dev/null
mv "$storage_file.partial" "$storage_file"

find "$BACKUP_DIR" -maxdepth 1 \( -name 'db-*.sql.gz' -o -name 'storage-*.tar.gz' \) -mtime +"$KEEP_DAYS" -delete

if [ -n "$BACKUP_SYNC_CMD" ]; then
  bash -c "$BACKUP_SYNC_CMD"
fi

echo "$(date -u +%FT%TZ) backup ok: $(basename "$db_file") $(du -h "$db_file" | cut -f1), $(basename "$storage_file") $(du -h "$storage_file" | cut -f1)"

if [ -n "$BACKUP_PING_URL" ]; then
  curl -fsS --retry 3 "$BACKUP_PING_URL" > /dev/null
fi
