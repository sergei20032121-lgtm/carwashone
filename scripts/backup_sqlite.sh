#!/usr/bin/env bash
set -euo pipefail

CONTAINER_NAME="${CONTAINER_NAME:-carwashone}"
HOST_DATA_DIR="${HOST_DATA_DIR:-/opt/carwashone-data}"
BACKUP_DIR="${BACKUP_DIR:-${HOST_DATA_DIR}/backups}"
KEEP_DAYS="${KEEP_DAYS:-30}"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
HOST_TARGET="${BACKUP_DIR}/carwash-${STAMP}.sqlite3"
CONTAINER_TARGET="/data/backups/carwash-${STAMP}.sqlite3"

mkdir -p "$BACKUP_DIR"
chmod 700 "$BACKUP_DIR"

if ! docker inspect "$CONTAINER_NAME" >/dev/null 2>&1; then
  echo "Контейнер ${CONTAINER_NAME} не найден" >&2
  exit 1
fi

docker exec -i "$CONTAINER_NAME" python - "$CONTAINER_TARGET" <<'PY'
import os
import sqlite3
import sys

source = "/data/carwash.db"
target = sys.argv[1]
temporary = target + ".tmp"

os.makedirs(os.path.dirname(target), exist_ok=True)
if os.path.exists(temporary):
    os.unlink(temporary)

with sqlite3.connect(source) as src, sqlite3.connect(temporary) as dst:
    src.backup(dst)

os.replace(temporary, target)
PY

chmod 600 "$HOST_TARGET"
sha256sum "$HOST_TARGET" > "${HOST_TARGET}.sha256"
chmod 600 "${HOST_TARGET}.sha256"

find "$BACKUP_DIR" -type f \( -name 'carwash-*.sqlite3' -o -name 'carwash-*.sqlite3.sha256' \) -mtime "+${KEEP_DAYS}" -delete

echo "Создан бэкап: ${HOST_TARGET}"
