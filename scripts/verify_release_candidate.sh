#!/usr/bin/env bash
set -euo pipefail

artifact_root="${ASSAY_ARTIFACT_ROOT:-dist/release}"
publisher_root="${ASSAY_PUBLISHER_ROOT:-dist/publish-tools}"
cleanup() {
  pnpm --dir ts clean >/dev/null 2>&1 || true
  rm -rf -- "$artifact_root" "$publisher_root"
}
trap cleanup EXIT

detected_node="$(node --version 2>/dev/null || true)"
if [[ "${detected_node}" != "v22.13.0" ]]; then
  printf 'release candidate requires Node 22.13.0; detected %s\n' "${detected_node:-unavailable}" >&2
  exit 1
fi
if [[ "$(pnpm --version 2>/dev/null || true)" != "11.5.0" ]]; then
  printf 'release candidate requires pnpm 11.5.0\n' >&2
  exit 1
fi
if [[ "$(python -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')" != "3.13" ]]; then
  printf 'release candidate requires Python 3.13\n' >&2
  exit 1
fi
if [[ "$(uv --version)" != uv\ 0.11.32* ]]; then
  printf 'release candidate requires uv 0.11.32\n' >&2
  exit 1
fi
if [[ "$(actionlint -version | head -1)" != "1.7.12" ]]; then
  printf 'release candidate requires actionlint 1.7.12\n' >&2
  exit 1
fi
if [[ "$(gitleaks version)" != "8.30.1" ]]; then
  printf 'release candidate requires Gitleaks 8.30.1\n' >&2
  exit 1
fi
shellcheck_version="$(shellcheck --version | awk '/^version:/ { print $2 }')"
printf 'release toolchain: Python 3.13, uv 0.11.32, actionlint 1.7.12, Gitleaks 8.30.1, ShellCheck %s\n' "$shellcheck_version"
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
bash scripts/build_release_artifacts.sh "$artifact_root"
bash scripts/stage_npm_publisher.sh "$publisher_root"
shellcheck examples/*.sh scripts/*.sh
cleanup
trap - EXIT
git diff --check
git diff --exit-code
test -z "$(git status --porcelain=v1 --untracked-files=all)"
