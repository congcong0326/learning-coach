#!/usr/bin/env bash
set -euo pipefail

frontend_url="${FRONTEND_URL:-http://localhost:${FRONTEND_PORT:-5173}}"

curl --fail --silent --show-error --output /tmp/learning-coach-frontend-smoke.html "${frontend_url}/"

if ! grep -q '<div id="root"></div>' /tmp/learning-coach-frontend-smoke.html; then
  echo "Frontend root element was not found in ${frontend_url}/" >&2
  exit 1
fi

echo "Frontend smoke passed at ${frontend_url}"
