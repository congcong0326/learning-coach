#!/usr/bin/env bash
set -euo pipefail

backend_url="${BACKEND_URL:-http://localhost:${BACKEND_PORT:-8000}}"
python_cmd=(${PYTHON_CMD:-uv run python})

health_response="$(curl --fail --silent --show-error "${backend_url}/health")"
api_health_response="$(curl --fail --silent --show-error "${backend_url}/api/health")"

"${python_cmd[@]}" - "$health_response" "$api_health_response" <<'PY'
import json
import sys

expected = {"status": "ok", "service": "learning-coach-backend"}

for raw in sys.argv[1:]:
    payload = json.loads(raw)
    if payload != expected:
        raise SystemExit(f"Unexpected backend health payload: {payload!r}")
PY

echo "Backend health smoke passed at ${backend_url}"
