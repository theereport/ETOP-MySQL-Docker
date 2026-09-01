#!/bin/sh
# Dumps the etop-db MySQL database to a gzipped, timestamped file and prunes
# backups older than BACKUP_RETENTION_DAYS. Run inside the `backup` compose
# service (see docker-compose.yml), which has mysqldump available via the
# mysql:8.0 image.
set -eu

: "${ETOP_DB_HOST:?ETOP_DB_HOST must be set}"
: "${ETOP_DB_NAME:?ETOP_DB_NAME must be set}"
: "${ETOP_DB_USER:?ETOP_DB_USER must be set}"
: "${ETOP_DB_PASSWORD:?ETOP_DB_PASSWORD must be set}"
ETOP_DB_PORT="${ETOP_DB_PORT:-3306}"
BACKUP_RETENTION_DAYS="${BACKUP_RETENTION_DAYS:-14}"
BACKUP_DIR="${BACKUP_DIR:-/backups}"

mkdir -p "$BACKUP_DIR"

timestamp=$(date -u +%Y%m%dT%H%M%SZ)
sql_tmp="$BACKUP_DIR/.etop-$timestamp.sql.tmp"
dump_path="$BACKUP_DIR/etop-$timestamp.sql.gz"

cleanup() {
  rm -f "$sql_tmp"
}
trap cleanup EXIT

# Dump to a plain temp file first and only gzip after mysqldump succeeds -
# `sh` has no `pipefail`, so `mysqldump | gzip` would silently produce a
# "successful" but truncated .sql.gz if mysqldump failed partway through.
MYSQL_PWD="$ETOP_DB_PASSWORD" mysqldump \
  --host="$ETOP_DB_HOST" \
  --port="$ETOP_DB_PORT" \
  --user="$ETOP_DB_USER" \
  --single-transaction \
  --routines \
  --triggers \
  --no-tablespaces \
  "$ETOP_DB_NAME" > "$sql_tmp"

gzip -c "$sql_tmp" > "$dump_path"
echo "Backup written to $dump_path"

find "$BACKUP_DIR" -name 'etop-*.sql.gz' -mtime "+$BACKUP_RETENTION_DAYS" -print -delete
