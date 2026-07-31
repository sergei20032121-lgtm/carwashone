#!/usr/bin/env bash
set -euo pipefail

APP_DIR="${APP_DIR:-/opt/carwashone}"

chmod 750 "$APP_DIR/scripts/backup_sqlite.sh" "$APP_DIR/scripts/update_server.sh"
chmod 750 "$APP_DIR/scripts/release_smoke.py"
install -m 0644 "$APP_DIR/deploy/carwashone-backup.service" /etc/systemd/system/carwashone-backup.service
install -m 0644 "$APP_DIR/deploy/carwashone-backup.timer" /etc/systemd/system/carwashone-backup.timer
systemctl daemon-reload
systemctl enable --now carwashone-backup.timer

echo "Серверные инструменты установлены."
systemctl list-timers carwashone-backup.timer --no-pager
