#!/usr/bin/env bash
set -euo pipefail

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

"${script_dir}/smoke_backend.sh"
"${script_dir}/smoke_database.sh"
"${script_dir}/smoke_frontend.sh"
"${script_dir}/smoke_code_runner.sh"

echo "All smoke checks passed"
