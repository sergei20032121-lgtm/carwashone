#!/usr/bin/env bash
set -euo pipefail

APP_DIR="${APP_DIR:-/opt/carwashone}"
COMPOSE_FILE="${COMPOSE_FILE:-compose.production.yml}"
HEALTH_URL="${HEALTH_URL:-http://127.0.0.1:8123/site/}"

cd "$APP_DIR"

if [[ -n "$(git status --porcelain)" ]]; then
  echo "Обновление остановлено: в репозитории есть локальные изменения." >&2
  git status --short
  exit 1
fi

"$APP_DIR/scripts/backup_sqlite.sh"
git fetch origin main
git pull --ff-only origin main
docker compose -f "$COMPOSE_FILE" build
docker compose -f "$COMPOSE_FILE" up -d

for _ in {1..20}; do
  if curl --fail --silent --show-error "$HEALTH_URL" >/dev/null; then
    docker compose -f "$COMPOSE_FILE" ps
    echo "Обновление завершено, health-check пройден."
    exit 0
  fi
  sleep 2
done

docker compose -f "$COMPOSE_FILE" logs --tail=100
echo "Новая версия не прошла health-check. Бэкап БД сохранён; проверьте логи выше." >&2
exit 1
