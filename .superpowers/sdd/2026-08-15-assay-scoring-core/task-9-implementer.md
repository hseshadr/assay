# Task 9 implementer report

> **TL;DR:** The local Task 9 candidate is implemented and committed. The complete release-candidate
> rehearsal is green under the exact Python, Node, pnpm, and uv toolchains. No tag, release,
> workflow dispatch, registry publication, repository setting, branch-protection setting, push, or
> pull request was created or changed. Hosted/protected-PR evidence is deliberately deferred to the
> independent review and remote phase.

## Immutable local candidate

- Implementation commit: `56e13bf778a92bed92e8ab5e27cf4f6091f22525`
- Implementation tree: `f9e2d0483cdfe759b1d5f16f28cffbf299e80678`
- Starting commit: `6756fbc41d5394f6b3395e0992a90f11ee065b67`
- Local compatibility ref: `release/avow-0.4.x` is exactly
  `3121df1af33a41b457faa2fd1ce84dc823950c39`.
- Toolchains: Python `3.13.5`, uv `0.11.32`, Node `22.13.0`, pnpm `11.5.0`.
- Privileged-lane publisher tool: npm `12.0.2`, staged without project install and pinned to
  SHA-512 `b885e890b9418fa1693544d05f53e64f9a73ec194837d4258b15fecdd692347b1dd2a517b1b0cbaf9d31cd8e92c3b70956bd2ecc72833a57b4b3098f5bfa7943`.

## RED evidence

The first focused environment/configuration witness was:

```text
uv run pytest --no-cov -q tests/test_workflow_contract.py \
  -k 'document_exact_runtime_settings or generic_secret_patterns or cool_all_dependency'
3 failed, 25 deselected
```

Failure buckets: obsolete signing/ledger environment settings plus missing ranking/default-loading
truth; product-specific key/audit-output ignores; and missing seven-day cooldowns for all three
Dependabot ecosystems. The identical focused command is now `3 passed, 25 deselected`.

The focused registry witness was:

```text
uv run pytest --no-cov -q tests/test_release_contract.py \
  -k 'bind_pypi or cross_channel or authoritative_404'
2 failed, 1 passed, 32 deselected
```

Failure buckets: missing PEP 740 filename/digest/trusted-publisher binding and missing npm
cross-channel/fail-closed registry behavior. The identical focused command is now
`3 passed, 32 deselected`.

The first combined workflow/release/security pass was `67 passed, 7 failed`. Its remaining buckets
were the old broad sdist contract, generated audit-output ignore behavior, and stale benchmark/CI
and dist-tag assertions. The final combined command is `74 passed in 200.59s`.

The first complete Python gate after implementation was `748 passed, 6 failed` at 94.30% coverage.
Those six failures were all executable contract drift: four npm digest/document build witnesses and
two strict Python/CLAUDE readability witnesses. The six-test focused regression run then passed
`6/6`, and the complete final gate passed.

Three new TypeScript scoring mutations initially survived their focused RED run:
`ts-minimum-selected-score-is-candidate-score`, `ts-request-hash-includes-term-order`, and
`ts-request-hash-includes-component-order`. After strengthening their behavioral guards and exact
mutation replacements, the same three fired `3/3`; the complete new TypeScript scoring set fired
`14/14`.

## GREEN evidence

The final local release candidate ran twice after all behavior changes, with the final run using:

```text
env PATH=<Node-22.13.0-bin>:<fixed-system-path> \
  ASSAY_ARTIFACT_ROOT=dist/release \
  bash scripts/verify_release_candidate.sh
```

It exited `0` and included:

- Python: `754 passed`, branch-aware coverage `94.30%`; Ruff, format, strict mypy, and Xenon Grade A
  all green. A complete `src/`, `scripts/`, and `benchmarks/` AST scan also proved every shipped
  Python function is at most 15 lines.
- TypeScript: `12/12` files and `160/160` tests; statements `98.19%`, branches `96.11%`, functions
  `100%`, lines `99.44%`; Biome, typecheck, and build green.
- Cross-runtime parity: Python `39/39`; TypeScript `2/2` files and `40/40` vector tests.
- Mutation: `120/120` guards fired (`89` pytest and `31` vitest); no survivor, crash, missing target,
  or false-green. Both complete suites passed before and after restoration, and the whole-tree
  byte/inventory comparison was exact.
- Installed example: Python and TypeScript results matched with the pinned input hash.
- Release contract: clean installs passed for the Python sdist, base wheel, `[cli]`, `[metrics]`,
  `[cli,metrics]`, and the npm root import; legacy npm subpaths remained unavailable.

## Committed-SHA benchmark evidence

All reports below contain exact SHA `56e13bf778a92bed92e8ab5e27cf4f6091f22525` and were captured
after the implementation commit on macOS 26.5 arm64. One-sample isolated workloads intentionally
report identical p50/p95/p99 values.

| Workload | Count | p50 ms | p95 ms | p99 ms | Peak RSS MiB |
|---|---:|---:|---:|---:|---:|
| Python composition batch | 2,000 | 168.441 | 169.168 | 169.168 | 38.844 |
| Python minimum compose + replay | 150,000 | 10,551.857 | 10,551.857 | 10,551.857 | 866.031 |
| Python binary measurement | 10,000, exactly 99 resamples | 744.189 | 744.189 | 744.189 | 130.797 |
| TypeScript composition batch | 2,000 | 74.437 | 93.511 | 93.511 | 58.625 |
| TypeScript minimum compose + replay | 150,000 | 2,623.612 | 2,623.612 | 2,623.612 | 790.406 |

The 10,000-item binary workload uses 990,000 bootstrap work cells, below the 10,000,000-cell cap.
Each 150,000-component workload runs in an isolated process.

## Artifact envelope and reproducibility

The committed-SHA release directory contained exactly `SHA256SUMS` plus three artifacts:

```text
b5464cdf2fac0b8525451dc5d96f9f9446e9b205d875c57be838fc6113b4c5c9  npm/edgeproc-assay-0.5.0-dev.0.tgz
0166b9691d43cd48194b7bd04227834c4a40feba5f83d3b75d83efe951c78913  python/assay_engine-0.5.0.dev0-py3-none-any.whl
cd0e7593513ff587389df34813b29f09b054f5fc4c9191e86ea0e4ffc28cb0fb  python/assay_engine-0.5.0.dev0.tar.gz
```

Two independent, locked, no-isolation Hatchling `1.27.0` builds produced byte-identical wheels and
sdists. The sdist has 29 files: `LICENSE`, `README.md`, `pyproject.toml`, generated `PKG-INFO`, and
exactly these 25 runtime files under `src/assay/`:

```text
__init__.py _cli_app.py _cli_io.py _json.py _optional.py _version.py
additive.py agreement.py calibration.py cli.py compose.py composite.py contracts.py errors.py
limits.py measurement.py metrics.py minimum.py models.py normalize.py py.typed ranking.py settings.py
uncertainty.py weighted_mean.py
```

The wheel has the same 25 `assay/` runtime files plus exactly `METADATA`, `WHEEL`,
`entry_points.txt`, `licenses/LICENSE`, and `RECORD` in its dist-info directory. The npm archive has
25 files: `LICENSE`, `README.md`, `package.json`, and `.js` plus `.d.ts` pairs for `additive`,
`compose`, `contracts`, `errors`, `index`, `metrics`, `minimum`, `normalize`, `ranking`,
`requestHash`, and `weightedMean` under `dist/`.

## Workflow, registry, and provenance contracts

- CI exposes exactly seven independently required jobs; security exposes exactly three.
- All jobs use `ubuntu-24.04`; action pins match the Task 9 brief; checkout never persists
  credentials. Publish has `permissions: {}` and package-wide non-cancelling concurrency.
- Stable/dev identity simulations accept only `X.Y.Z`/`vX.Y.Z` and
  `X.Y.Z.devN`/`X.Y.Z-dev.N`/`vX.Y.Z-dev.N`; leading-zero, post, local, alpha, beta, rc, alternative,
  and divergent identities fail closed.
- Registry simulations cover authoritative 404-only absence, malformed/partial/conflicting/5xx/
  timeout failure, exact-byte retry skips, PEP 740 publisher binding, npm SLSA subject/repository/
  workflow/tag/SHA binding, stable `latest`, prerelease `next`, historical version-specific tags,
  tag collision, overlapping/out-of-order releases, and no rollback.
- The npm OIDC lane has no checkout, project install, build, test, or project-source execution. It
  verifies and directly invokes only the staged npm `12.0.2` CLI, immediately rechecks registry
  channel state, and publishes once under the preflight-selected tag. It never relies on a later
  `dist-tag` mutation.
- Final verification runs for every publish/skip combination only when both preflights succeeded
  and each publisher succeeded or was skipped; it rejects failed or cancelled dependencies.

## Supply-chain evidence

- actionlint `1.7.12`: green.
- zizmor `1.29.0`, pedantic, low severity, offline, strict collection over `.github`: no findings.
- Gitleaks `8.30.1`: 172 commits / approximately 2.26 MiB full history and approximately 3.83 MiB
  current tree scanned; no leaks.
- The only historical match is ignored by one exact fingerprint with rationale
  `documented Ed25519 public key test vector; not secret`. Tests reject broad rule, path, or history
  allowlists.
- pip-audit `2.10.1` over the frozen hashed export: no known vulnerabilities.
- pnpm locked audit at `high`: no known vulnerabilities.
- ShellCheck over `examples/*.sh` and `scripts/*.sh`: green.
- Dependabot uses a seven-day cooldown for GitHub Actions, npm, and pip.

## Explicitly deferred remote evidence

This task stopped at the authorized clean local candidate. Hosted run/check IDs, draft PR,
protection changes, independent Northstar grade/findings, remote compatibility-ref verification,
merge SHA/tree parity, and post-merge state are not claimed here. The local repository's existing
tags were left unchanged, and neither candidate package was published.
