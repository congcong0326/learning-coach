#!/usr/bin/env bash
set -euo pipefail

host="${POSTGRES_HOST:-postgres}"
port="${POSTGRES_PORT:-5432}"
timeout_seconds="${WAIT_FOR_DB_TIMEOUT:-60}"
python_cmd=(${PYTHON_CMD:-uv run python})

deadline=$((SECONDS + timeout_seconds))

while (( SECONDS < deadline )); do
  if "${python_cmd[@]}" - "$host" "$port" <<'PY'
import socket
import sys

host = sys.argv[1]
port = int(sys.argv[2])

with socket.create_connection((host, port), timeout=2):
    pass
PY
  then
    echo "Database is reachable at ${host}:${port}"
    exit 0
  fi

  sleep 1
done

echo "Timed out waiting for database at ${host}:${port}" >&2
exit 1
