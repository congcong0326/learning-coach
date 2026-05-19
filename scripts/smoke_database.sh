#!/usr/bin/env bash
set -euo pipefail

backend_url="${BACKEND_URL:-http://localhost:${BACKEND_PORT:-8000}}"
compose_file="${COMPOSE_FILE:-infra/compose/docker-compose.dev.yml}"
postgres_user="${POSTGRES_USER:-learning_coach}"
postgres_db="${POSTGRES_DB:-learning_coach}"
python_cmd=(${PYTHON_CMD:-uv run python})

db_health_response="$(curl --fail --silent --show-error "${backend_url}/api/db/health")"

"${python_cmd[@]}" - "$db_health_response" <<'PY'
import json
import sys

payload = json.loads(sys.argv[1])
expected = {"status": "ok", "database": "reachable"}

if payload != expected:
    raise SystemExit(f"Unexpected database health payload: {payload!r}")
PY

extension_count="$(
  docker compose -f "${compose_file}" exec -T postgres \
    psql -U "${postgres_user}" -d "${postgres_db}" -tAc \
    "select count(*) from pg_extension where extname = 'vector';"
)"

if [[ "${extension_count}" != "1" ]]; then
  echo "pgvector extension was not found" >&2
  exit 1
fi

echo "Database smoke passed"
