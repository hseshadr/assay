#!/usr/bin/env bash
set -euo pipefail

destination="${1:?usage: build_python_artifacts.sh DESTINATION}"
comparison="$(mktemp -d "${TMPDIR:-/tmp}/assay-python-build.XXXXXX")"
trap 'rm -rf -- "${comparison}"' EXIT INT TERM
rm -rf -- "$destination"
mkdir -p -- "$destination"
SOURCE_DATE_EPOCH="$(git log -1 --pretty=%ct)"
export SOURCE_DATE_EPOCH
uv build --no-build-isolation --wheel --sdist --out-dir "$destination"
uv build --no-build-isolation --wheel --sdist --out-dir "$comparison"
rm -f -- "$destination/.gitignore" "$comparison/.gitignore"
uv run python scripts/minimize_sdist.py "$destination"/*.tar.gz
uv run python scripts/minimize_sdist.py "$comparison"/*.tar.gz
for artifact in "$destination"/*; do
  cmp -- "$artifact" "$comparison/$(basename "$artifact")"
done
