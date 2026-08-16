# Assay scoring engine

Assay turns measurements on different scales into one explained score. This repository contains
only scoring code; signed evidence and receipts belong to the separate Avow project.

## Commands

```bash
uv sync --all-extras
uv run poe gate
uv run poe mutants

corepack pnpm --dir ts install --frozen-lockfile
corepack pnpm --dir ts gate
corepack pnpm --dir ts audit --audit-level low
corepack pnpm --dir ts pack
```

Use Node 22.13 and the `pnpm@11.5.0` pinned in `ts/package.json`. The ambient Node or pnpm may be
newer and can produce different package artifacts.

## Layout

- `src/assay/` — Python contracts, normalization, combiners, metrics, and CLI.
- `ts/src/` — dependency-free TypeScript scoring package and tests.
- `testdata/vectors/` — shared Python/TypeScript parity fixtures.
- `tests/` — Python behavior, boundary, packaging, and workflow tests.
- `scripts/mutation_harness.py` — breaks guards deliberately and requires their tests to fail.

## Contracts

- Public inputs are finite IEEE-754 binary64 numbers. Both runtimes canonicalize zero to `+0`.
- Hashes encode every number as big-endian binary64 bits and preserve declared input order.
- `weighted_mean`, `additive`, and `minimum` are separate methods. Additive arithmetic is strictly
  left-to-right; minimum ties select the first declared component.
- Unknown inputs and serialized results are parsed strictly. Errors use stable, value-free
  `assay.*` codes.
- Keep scoring independent of signing, evidence, receipts, ledgers, persistence, and network I/O.

## Workflow

- Use red -> green -> refactor. A behavior change starts with a failing test.
- Run both language gates after shared-contract changes; current CI is intentionally Python-only
  until the TypeScript release lane is restored.
- Keep TypeScript scoring modules above 90% branch, function, and line coverage per file.
- `@edgeproc/assay@0.5.0-dev.0` is an unpublished local candidate. Do not publish, tag, or change
  release settings without explicit approval.
