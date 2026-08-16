# Task 9 implementer report

> **TL;DR:** Task 9 and its review corrections are committed as a clean local candidate. The
> complete release-candidate rehearsal passed under the exact pinned toolchains. No tag, release,
> workflow dispatch, registry publication, push, pull request, repository setting, or branch
> protection was created or changed. Remote evidence remains deliberately deferred to independent
> review.

## Immutable local candidate

- Corrected source candidate: `cb8983c5b8d305a6693d2568a3bf9060b70be894`
- Corrected source tree: `fcb980e91dc535b25d7b7ebe88c4b9793299b7f8`
- Correction commits: `d56b737e3f3f440665058652074ddf18ee26e51e` and
  `cb8983c5b8d305a6693d2568a3bf9060b70be894`
- Review baseline: `41e5e9105769c9d48631db037f16a7c3dddb9842`
- Task baseline: `6756fbc41d5394f6b3395e0992a90f11ee065b67`
- Local compatibility ref: `release/avow-0.4.x` is exactly
  `3121df1af33a41b457faa2fd1ce84dc823950c39`.
- Toolchains: Python `3.13.5`, uv `0.11.32`, Node `22.13.0`, pnpm `11.5.0`, actionlint
  `1.7.12`, Gitleaks `8.30.1`, ShellCheck `0.11.0`, and zizmor `1.29.0`.
- Privileged publisher tool: npm `12.0.2`, staged without a project install. The workflow itself
  carries the immutable SHA-512 trust root
  `b885e890b9418fa1693544d05f53e64f9a73ec194837d4258b15fecdd692347b1dd2a517b1b0cbaf9d31cd8e92c3b70956bd2ecc72833a57b4b3098f5bfa7943`.

## Correction RED evidence

The first focused review-correction witness selected 27 behavioral tests / 32 parametrized cases:

```text
uv run pytest --no-cov -q \
  tests/test_release_contract.py tests/test_workflow_contract.py \
  tests/test_workflow_security.py \
  -k "accept_exact_stable or peel_the_release_tag or release_tag_pointing or \
  hosted_sha_different or accept_only_an_exact_release_identity or duplicate_pypi or \
  verify_real_release_artifacts or renamed_release_artifacts or duplicate_wheel or \
  nonregular_tar or typescript_peak_rss or materialize_and_verify or \
  retry_only_authoritative or fail_immediately_on_permanent or bound_http_and_sleep or \
  inventory_ignored or remove_every_generated or describe_only_current or \
  bind_every_action or rehearse_the_installed or stage_npm_with_a_present or \
  pin_python_313 or privileged_channel_recheck or bound_final_polling or \
  rebuild_uploadable or provision_exact_clean or document_the_single_internal"
32 failed, 1 warning in 46.31s
```

Named failure buckets were:

- release-tag identity: lightweight and annotated tag peeling, tag-to-HEAD mismatch, and hosted-SHA
  mismatch;
- source-derived filenames and archive safety: renamed wheel/sdist/tgz, duplicate ZIP members, and
  sdist/npm links or other non-regular members;
- registry safety: duplicate PyPI filenames, actual served-byte materialization, global deadline,
  retry-only absence, and immediate permanent mismatch;
- TypeScript peak RSS: actual Linux high-water measurement rather than a sampled current value;
- cleanup and stale contract text: ignored release-output inventory, exit cleanup, and obsolete
  Avow/vector framing;
- hosted workflow contracts: action version annotations, dependency-clean all-extras rehearsal,
  portable Darwin npm checksum staging, exact Python observers, fail-closed channel recheck,
  bounded final verification, post-gate rebuild, clean served-artifact installs, and the one internal
  publisher invariant.

The later resource/reproducibility witness was:

```text
uv run pytest --no-cov -q tests/test_release_contract.py tests/test_workflow_contract.py \
  -k "derive_the_build_epoch or bound_registry_json or bound_served_artifacts or \
  use_five_isolated or time_out_a_hung_python or pin_and_record_every_local_release_tool or \
  bound_the_hosted_benchmark or name_only_the_unpublished"
10 failed in 1.58s
```

Its buckets were source-only build epoch, absent/lying Content-Length metadata and artifact caps,
five-sample percentile distributions, hung-child timeouts, exact local tools, hosted benchmark job
timeout, and exact unpublished-candidate SECURITY wording. Together the correction witnesses were
42 failing cases before implementation.

The first combined correction GREEN pass was `112 passed, 1 warning in 375.69s`. The warning came
only from deliberately constructing a duplicate ZIP member; it is now captured and asserted. Its
focused warnings-as-errors replay passed `1 passed in 40.03s`, and the final complete gate reports
no warnings.

## Final release-candidate evidence

The clean source candidate ran:

```text
PATH=<Node-22.13.0-bin>:<pnpm-11.5.0-wrapper>:<fixed-system-path> \
  uv run poe release-candidate
```

It exited `0` and cleaned every generated release and publisher output. Evidence within that one
run:

- Python: `792 passed in 469.85s`, zero warnings, branch-aware coverage `94.30%`; Ruff, format,
  strict mypy, Xenon Grade A, and the 15-line shipped-function contract all green.
- TypeScript: `12/12` files and `160/160` tests; statements `98.19%`, branches `96.11%`, functions
  `100%`, lines `99.44%`; Biome, typecheck, and build green.
- Cross-runtime parity: Python `39/39`; TypeScript `2/2` files and `40/40` vectors.
- Mutation: `120/120` guards fired. Both complete suites passed before mutation and after byte-exact
  restore; `pytest=0`, `pnpm=0`, and `whole-tree exact=True`. There was no survivor, crash, missing
  target, or false-green.
- Installed example: Python and TypeScript fields and values matched with pinned input hash
  `sha256:0266b1c59c97bacf85dc945685c55bb4386856b525249c7d5663a8edf020ba06`.
- Artifact verification: Python sdist, base wheel, `[cli]`, `[metrics]`, `[cli,metrics]`, plus npm
  root, parity, and legacy-closure probes all passed from clean installs.

## Five-sample benchmark evidence

Every heavy scenario uses five independent child processes, nearest-rank percentiles, per-child
timeouts, and actual per-child high-water RSS. The CI benchmark job also has a 15-minute bound.
These reports contain exact source SHA `cb8983c5b8d305a6693d2568a3bf9060b70be894`:

| Workload | Count | Samples | p50 ms | p95 ms | p99 ms | Peak RSS MiB |
|---|---:|---:|---:|---:|---:|---:|
| Python composition batch | 2,000 | 5 | 179.892 | 181.264 | 181.264 | 38.406 |
| Python minimum compose + replay | 150,000 | 5 | 10,626.642 | 10,677.305 | 10,677.305 | 898.563 |
| Python binary measurement | 10,000 | 5 | 509.972 | 861.820 | 861.820 | 130.766 |
| TypeScript composition batch | 2,000 | 5 | 93.639 | 96.998 | 96.998 | 58.438 |
| TypeScript minimum compose + replay | 150,000 | 5 | 2,573.123 | 2,597.820 | 2,597.820 | 810.828 |

The binary workload explicitly uses 99 resamples: 990,000 bootstrap work cells, below the
10,000,000-cell cap.

## Artifact envelope and reproducibility

Two independent complete builds from the corrected immutable source were recursively byte-equal.
The source-date epoch is derived only from the latest commit touching packaged Python inputs, so
this report-only commit cannot perturb the wheel or sdist. The exact envelope is:

```text
b5464cdf2fac0b8525451dc5d96f9f9446e9b205d875c57be838fc6113b4c5c9  npm/edgeproc-assay-0.5.0-dev.0.tgz
0166b9691d43cd48194b7bd04227834c4a40feba5f83d3b75d83efe951c78913  python/assay_engine-0.5.0.dev0-py3-none-any.whl
cd0e7593513ff587389df34813b29f09b054f5fc4c9191e86ea0e4ffc28cb0fb  python/assay_engine-0.5.0.dev0.tar.gz
```

The preflight derives those filenames independently from source identity. A recomputed manifest
cannot legitimize renamed files, duplicate ZIP/tar records, extra archive records, links, devices,
absolute/traversal paths, or any non-regular member. Hatchling is exactly `1.27.0`, and Python
builds use the locked, no-isolation path.

## Registry and privileged-lane contracts

- Release identity peels `refs/tags/$RELEASE_TAG^{commit}` and requires that target, checked-out
  `HEAD`, and `GITHUB_SHA` to be identical before any publication decision.
- Metadata reads are streamed under 1 MiB, including when Content-Length is absent or dishonest.
  Artifact downloads accept only trusted registry hosts and exactly the reviewed local byte size.
- Final verification has one monotonic 600-second deadline covering HTTP, sleeps, downloads, and
  clean installs. Only an authoritative 404/propagation absence is retried; malformed state,
  conflicts, digest drift, provenance drift, cross-channel state, and HTTP errors fail immediately.
- Final verification downloads the wheel, sdist, and npm tarball actually served by the registries,
  checks the reviewed SHA envelope, validates subject digest plus repository/workflow/tag/SHA
  provenance, and performs every clean consumer install against those downloaded bytes.
- The npm OIDC job has no checkout, project install, build, test, or project-source execution. It
  verifies the staged npm `12.0.2` tarball against the hard-coded workflow trust root and invokes
  that CLI directly. It never runs arbitrary `npm install`.
- Stable releases use `latest`; prereleases use `next`. An absent historical target publishes under
  an immutable version-specific non-default tag when the channel is already newer. No retry or
  out-of-order writer may move a channel backward.
- The package-wide, non-cancelling release workflow is the only internal publisher invariant. An
  immediate authoritative channel recheck precedes publish, and final verification fails if
  external registry state violates the invariant.
- Final verification is explicitly scheduled for all four Python/npm publish-or-skip combinations
  and rejects every failed or cancelled dependency.

## Supply-chain evidence

- actionlint `1.7.12`: green.
- zizmor `1.29.0`, pedantic, low severity, offline, strict collection over `.github`: no findings.
- Gitleaks `8.30.1`: 176 commits / approximately 2.47 MiB full history and approximately 4.00 MiB
  current tree scanned; no leaks.
- The sole historical false positive is ignored only by its exact fingerprint, with rationale
  `documented Ed25519 public key test vector; not secret`. Tests reject broad rule, path, or history
  exclusions.
- pip-audit `2.10.1` over the frozen hashed export: no known vulnerabilities.
- pnpm locked audit at `high`: no known vulnerabilities.
- ShellCheck `0.11.0` over `examples/*.sh` and `scripts/*.sh`: green.
- Dependabot uses a seven-day cooldown for GitHub Actions, npm, and pip.

## Explicitly deferred remote evidence

This task stops at the authorized clean local candidate. Hosted run/check IDs, pull requests,
protection changes, remote compatibility-ref verification, merge SHA/tree parity, tags, releases,
and registry publication are not claimed. Existing tags and all registries were left unchanged.
