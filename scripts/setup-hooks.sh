#!/bin/sh
set -eu

cd "$(dirname "$0")/.."
if ! command -v uv >/dev/null 2>&1; then
    echo "uv is required on PATH. Install it first." >&2
    exit 1
fi
git config --local core.hooksPath .githooks
echo "Git hooks enabled: pre-commit runs Black with Python 3.15 via uv."
