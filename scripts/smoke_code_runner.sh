#!/usr/bin/env bash
set -euo pipefail

compose_file="${COMPOSE_FILE:-infra/compose/docker-compose.dev.yml}"

output="$(
  docker compose -f "${compose_file}" run --rm --no-deps \
    --entrypoint python code-runner \
    -I -c 'print(sum([20, 22]))'
)"

if [[ "${output}" != "42" ]]; then
  echo "Unexpected code-runner output: ${output}" >&2
  exit 1
fi

echo "Code-runner smoke passed"
