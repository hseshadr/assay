#!/usr/bin/env bash
set -euo pipefail

artifact_root="${1:-dist/release}"
rm -rf -- "${artifact_root}"
mkdir -p "${artifact_root}/python" "${artifact_root}/npm"

bash scripts/build_python_artifacts.sh "${artifact_root}/python"
pnpm --dir ts build
pnpm --dir ts pack --pack-destination "$(cd "${artifact_root}/npm" && pwd -P)"
uv run python scripts/verify_release_artifacts.py "${artifact_root}"
