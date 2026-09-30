#!/bin/sh
# Заглушка HTTP: GET /health → ok. Замените процесс в Dockerfile (target runtime).
set -eu
PORT="${PORT:-8080}"
ROOT="$(mktemp -d)"
trap 'rm -rf "$ROOT"' EXIT INT TERM
printf 'ok\n' > "${ROOT}/health"
exec busybox httpd -f -p "${PORT}" -h "${ROOT}"
