#!/usr/bin/env bash
set -euo pipefail

detected_node="$(node --version 2>/dev/null || true)"
if [[ "${detected_node}" != "v22.13.0" ]]; then
  printf 'release candidate requires Node 22.13.0; detected %s\n' "${detected_node:-unavailable}" >&2
  exit 1
fi
if [[ "$(pnpm --version 2>/dev/null || true)" != "11.5.0" ]]; then
  printf 'release candidate requires pnpm 11.5.0\n' >&2
  exit 1
fi
uv sync --frozen --all-groups --all-extras
pnpm --dir ts install --frozen-lockfile --ignore-scripts

uv run poe gate
pnpm --dir ts gate
uv run pytest tests/test_consumer_conformance.py tests/test_metric_vectors.py -q
pnpm --dir ts exec vitest run src/compositionVectors.test.ts src/metricVectors.test.ts
uv run poe mutants
uv run python -m benchmarks.release
pnpm --dir ts benchmark
bash examples/run_composite.sh

uv run poe workflow-lint
uv run poe workflow-security
uv run poe secrets
uv run poe audit
bash scripts/build_release_artifacts.sh "${ASSAY_ARTIFACT_ROOT:-dist/release}"
bash scripts/stage_npm_publisher.sh dist/publish-tools
shellcheck examples/*.sh scripts/*.sh
pnpm --dir ts clean
git diff --check
if [[ "${CI:-false}" == "true" ]]; then
  git diff --exit-code
fi
