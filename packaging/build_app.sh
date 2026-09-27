#!/bin/sh
set -eu
SOURCE_ROOT="$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)"
cd "$SOURCE_ROOT"
# macOS runtime and capture regressions must pass before a native rebuild.
uv run --frozen python -B -m unittest discover -s tests
uv run --frozen python packaging/build_app.py --output "${1:-$SOURCE_ROOT/dist}"
