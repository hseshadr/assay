# Task 6 implementer report

## Outcome

Replaced the TypeScript Avow product with the unpublished `@edgeproc/assay@0.5.0-dev.0`
candidate. The package now has one job: validate scoring inputs, normalize measurements, combine
them with an explicit method, and return a complete explanation.

The public package contains weighted mean, additive, and first-minimum composition; strict
unknown-input and result parsers; stable value-free `assay.*` errors; deterministic Python-parity
input hashes; and the intentionally retained pure ranking/classification metrics. It contains no
key, signature, receipt, canonicalization, evidence, ledger, Writ, persistence, environment,
filesystem, or network API. The former receipt UI workspace and Avow runtime were removed.

Implementation commit: `1713355ac73502eb221730e41f4d475ecf766a12`.

## Sequential TDD evidence

Clean base: `9d867bd750f2aca11590db7b3790d12b91de2bef`.

1. **Package boundary RED:** both focused assertions failed because the package was
   `@edgeproc/avow@0.4.1`, carried evidence dependencies, and exported evidence APIs. GREEN:
   `2/2` passed for the Assay identity, empty runtime dependency set, scoring exports, and closed
   evidence surface.
2. **Contract/parser RED:** the first valid request had no parser; after the initial shell, the
   expanded boundary suite had `13 failed / 15`. GREEN: `15/15` focused contract tests passed,
   followed by boundary-mutation coverage for malformed containers, unknown/missing fields,
   booleans and nonfinite/unsafe numbers, invalid Unicode scalars, identifiers, labels, scales,
   intervals, weights, coefficients, enums, duplicate IDs, reject-policy ranges, forged result
   shapes, and method-incoherent result replay.
3. **Normalization RED:** the shared-vector test failed because `normalize` did not exist. GREEN:
   all `9/9` shared Python vector rows executed, including fractional binary64 behavior and both
   signed-zero cases.
4. **Weighted mean RED:** the focused behavior test failed because the combiner did not exist.
   GREEN: normalization, declared-order weight addition, exact `weight / weight_total`
   coefficients, contribution intervals, metadata, hash, and result replay passed.
5. **Additive RED:** the focused behavior test failed because the combiner did not exist. GREEN:
   intercept, explicit add/subtract operations, strict left-to-right arithmetic, interval endpoint
   reversal for subtraction, and final-only clamp/reject behavior passed.
6. **Minimum RED:** the focused behavior test failed because the combiner did not exist. GREEN:
   normalization, interval propagation, selected ID, and first-declared tie selection passed.
7. **Composition/hash/replay RED:** `3/4` focused tests failed before dispatch and exact hash/result
   parity existed. GREEN: `4/4` passed against all five complete shared results, all five pinned
   hashes, result-only replay for every method, field/order hash changes, signed-zero
   canonicalization, and final-only additive clamping.
8. **Tarball RED:** the artifact test initially failed because no Assay license/package artifact
   existed and Avow text/runtime remained. GREEN: `2/2` real-artifact tests passed for exact
   membership, contamination checks, clean install, all methods, result replay, and forbidden
   legacy subpaths.
9. **Coverage RED:** the first full core run reported `83.24%` branch coverage. Additional
   behavior-level boundary and mutation-strength cases raised the final result to `91.22%` branch
   coverage without excluding core files.
10. **Dependency audit RED:** pnpm reported one high-severity `nanoid` advisory in test tooling.
    The lock was regenerated with a narrow exact `nanoid@3.3.18` override. GREEN output is
    `No known vulnerabilities found` at `--audit-level low`; the packed runtime has zero
    dependencies.

The final Task 6 focused suite is `49 passed` across the nine new package/contract/composition/
artifact test files. The complete TypeScript suite is `121 passed` across `12` files.

## Python and TypeScript parity

The shared composition vector ID set is identical in both runtimes and was asserted exactly, not
as a non-empty smoke test:

1. `northstar_uncapped_weighted`
2. `edgereco_recommendation`
3. `amlfilter_match_confidence`
4. `almamesh_domain_strength_forward_tie`
5. `almamesh_domain_strength_reverse_tie`

For every ID, TypeScript produces a `JSON.stringify`-byte-equivalent result to Python, including
all keys, explicit nulls, declaration order, component rows, intervals, weight metadata,
intercept/clamp metadata, selected ID, and input hash. The two AlmaMesh vectors reverse an equal
minimum and therefore prove declaration-order selection. The normalization file has no ID field;
both runtimes execute all nine rows and the TypeScript test fails if its length is not exactly
nine.

The five pinned result hashes are:

- `northstar_uncapped_weighted`: `sha256:0266b1c59c97bacf85dc945685c55bb4386856b525249c7d5663a8edf020ba06`
- `edgereco_recommendation`: `sha256:df9b86d02e3cabea42e98ef18df165f6f8a227f8f144ae430496a43b5fcdc5fb`
- `amlfilter_match_confidence`: `sha256:64cecab703da9d0f2a473ad4a14c4ccb96b683d9b20169d1dcd650892eba0ff6`
- `almamesh_domain_strength_forward_tie`: `sha256:c1dd2da5ebd54dfcc6f3b250f118ce1fc6ce7f3dfc7d249cf7a5f7216d4eaa5e`
- `almamesh_domain_strength_reverse_tie`: `sha256:09c0694100a04d66119ca5712cb669459e7bece368e36f729d2bb1c98f4f1115`

No shared vector was changed.

## Tarball and clean-install evidence

Two independent Node 22.13.0 builds produced the same archive SHA-256:

`760dfc22d933c130d0eaa9b8167306bb39203693ff30aab37ce87e7abb8e0c8e`

Exact archive membership (`25` entries):

```text
package/LICENSE
package/README.md
package/dist/additive.d.ts
package/dist/additive.js
package/dist/compose.d.ts
package/dist/compose.js
package/dist/contracts.d.ts
package/dist/contracts.js
package/dist/errors.d.ts
package/dist/errors.js
package/dist/index.d.ts
package/dist/index.js
package/dist/metrics.d.ts
package/dist/metrics.js
package/dist/minimum.d.ts
package/dist/minimum.js
package/dist/normalize.d.ts
package/dist/normalize.js
package/dist/ranking.d.ts
package/dist/ranking.js
package/dist/requestHash.d.ts
package/dist/requestHash.js
package/dist/weightedMean.d.ts
package/dist/weightedMean.js
package/package.json
```

The artifact test created a blank application, installed the `.tgz` with Node 22 and the pinned
pnpm 11.5.0, imported only `@edgeproc/assay`, composed all five vectors, compared every complete
result, parsed every serialized result independently, and proved `receipt`, `keys`, `canonical`,
`ledger`, and `writ` subpaths do not resolve. A separate README rehearsal used a blank npm app and
produced the documented `0.8525` score.

Tarball text contains no Avow runtime symbol, legacy dependency name, receipt UI, or Writ content.
The only Avow mention is the README's one-sentence product boundary.

## Final verification

All Node commands used Node `22.13.0` and repository-pinned pnpm `11.5.0`.

- Frozen TypeScript install: passed.
- Biome lint: passed (`29 files`, no fixes).
- Strict TypeScript typecheck: passed.
- Vitest: `12 files / 121 tests passed`.
- TypeScript coverage: `95.68%` statements, `91.22%` branches, `99.40%` functions,
  `96.73%` lines.
- TypeScript build: passed.
- Real pack, exact membership, clean install, and root-import test: passed.
- `pnpm audit --audit-level low`: `No known vulnerabilities found`.
- Focused Python parity gate: `42 passed`.
- Full Python `uv run poe gate`: `435 passed`; Ruff, strict mypy, Xenon, and the `94.08%`
  Python coverage gate passed.
- `git diff --check`: passed before commit.
- `.pnpm-debug.log` is absent and now regression-excluded by the root `.gitignore`.

## Deviations and external actions

- Ambient shell tooling was Node 26 with an incompatible Corepack/pnpm selection, so every proof
  used the installed supported Node `22.13.0` binary and exact pinned pnpm `11.5.0`.
- The implementation commit includes the root `.gitignore` line for `.pnpm-debug.log`, requested
  during execution after a transient pnpm debug file appeared. That file was deleted before the
  commit. No unrelated root file changed.
- No TypeScript mutation-runner integration was added because the program assigns that CI/release
  wiring to Task 9. Task 6 added direct mutation-strength regressions for every listed semantic
  boundary, and the final branch floor is enforced without exclusions.
- No push, tag, npm/PyPI publication, Dependabot merge, release, workflow dispatch, remote
  mutation, or repository-setting change was performed.

Remaining Task 6 failures: none.
