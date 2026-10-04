#!/usr/bin/env bash
set -euo pipefail

# Run after transferring the project, .env and consistent account backup.
ROOT=/srv/trading_bot_full
PROJECT="$ROOT/Trading Bot"
test "$(id -u)" -eq 0 || { echo 'Run with sudo.'; exit 1; }
test -f "$PROJECT/.env" || { echo 'Transfer the project .env securely first.'; exit 1; }
test -f "$PROJECT/frontend/dist/index.html" || { echo 'Build and transfer frontend/dist first.'; exit 1; }
test -f "$PROJECT/backend/trading_bot.db" || { echo 'Transfer the consistent paper-account database backup first.'; exit 1; }
mkdir -p "$ROOT/.tmp" "$ROOT/.cache/pip" "$ROOT/logs"
export TMPDIR="$ROOT/.tmp" TMP="$ROOT/.tmp" TEMP="$ROOT/.tmp"
export PIP_CACHE_DIR="$ROOT/.cache/pip" PYTHONDONTWRITEBYTECODE=1
apt-get update
apt-get install -y python3-venv nginx
id paperbot >/dev/null 2>&1 || useradd --system --home-dir "$ROOT" --shell /usr/sbin/nologin paperbot
python3 -m venv "$PROJECT/backend/.venv"
"$PROJECT/backend/.venv/bin/python" -B -m pip install -r "$PROJECT/backend/requirements.txt"
chown -R paperbot:paperbot "$ROOT"
chmod 600 "$PROJECT/.env"
chmod -R o+rX "$PROJECT/frontend/dist"
install -m 644 "$PROJECT/deploy/oracle/paperbot.service" /etc/systemd/system/paperbot.service
install -m 644 "$PROJECT/deploy/oracle/nginx.conf" /etc/nginx/conf.d/paperbot.conf
nginx -t
systemctl daemon-reload
systemctl enable paperbot nginx
systemctl restart nginx
echo 'Installed. Start paperbot only after the local engine is stopped:'
echo 'sudo systemctl start paperbot'
echo 'curl --fail http://127.0.0.1:8080/api/health'
