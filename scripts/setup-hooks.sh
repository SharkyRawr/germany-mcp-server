#!/bin/sh
set -eu

cd "$(dirname "$0")/.."
if ! command -v black >/dev/null 2>&1; then
    echo "Black is required on PATH. Install it system-wide first." >&2
    exit 1
fi
git config --local core.hooksPath .githooks
echo "Git hooks enabled: pre-commit runs the system Black formatter."
