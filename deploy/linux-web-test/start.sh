#!/bin/sh
set -eu
cd "$(dirname "$0")"
if [ ! -f .env ]; then
  PASS="$(python3 - <<'PY'
import secrets
print('Web!'+secrets.token_urlsafe(12)+'9a')
PY
)"
  umask 077
  printf 'HRM_INITIAL_PASSWORD=%s\nHRM_WEB_PORT=8080\n' "$PASS" > .env
  echo "Created local test credentials in .env (mode 600)."
  echo "Initial user: arshia.shahbazi"
  echo "Initial password: $PASS"
  echo "Change it immediately after first login."
fi
docker compose up --build -d
echo "HRM Linux Web Test: http://127.0.0.1:8080/"
