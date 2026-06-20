#!/usr/bin/env bash
set -euo pipefail

BACKUP_ROOT="${BACKUP_ROOT:-/home/scs_dev/velora/backups/prod}"
DB_NAME="${SORIMEMO_DB_NAME:-${DB_NAME:-sorimemo_prod}}"
RETENTION_DAYS="${RETENTION_DAYS:-14}"
STAMP="$(date +%Y%m%d-%H%M%S)"
DEST="${BACKUP_ROOT}/${STAMP}"

mkdir -p "${DEST}"
chmod 700 "${BACKUP_ROOT}" "${DEST}"

run_as_postgres() {
  if command -v sudo >/dev/null 2>&1; then
    sudo -u postgres "$@"
  else
    su -s /bin/sh postgres -c "$(printf '%q ' "$@")"
  fi
}

run_as_postgres pg_dump -Fc "${DB_NAME}" > "${DEST}/${DB_NAME}.dump"
run_as_postgres pg_dump -s "${DB_NAME}" > "${DEST}/${DB_NAME}_schema.sql"

tar -czf "${DEST}/sorimemo_prod_config.tgz" \
  /etc/nginx/sites-available/sorimemo \
  /etc/systemd/system/sorimemo-prod-api.service \
  /etc/sorimemo-prod-api.env \
  /home/scs_dev/velora/ops/prod/prod_schema.sql \
  /home/scs_dev/velora/ops/prod/rebuild_prod.sh

sha256sum "${DEST}"/* > "${DEST}/SHA256SUMS"
find "${BACKUP_ROOT}" -mindepth 1 -maxdepth 1 -type d -mtime +"${RETENTION_DAYS}" -exec rm -rf {} +

echo "Backup complete: ${DEST}"
