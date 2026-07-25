# CLAUDE.md

Guidance for Claude Code working in this repository.

## What this repo is

The **trust-kernel monorepo**: one Python distribution named `avow` exposing three import
packages, plus a TypeScript surface.

- **`avow`** (`src/avow/`) — the shared signed-receipt **envelope**: RFC 8785 (JCS)
  canonicalization + SHA-256 content hash + Ed25519 sign/verify, subject-agnostic, plus
  key custody and an append-only content-addressed ledger. Depends only on pydantic,
  pynacl, rfc8785.
- **`assay`** (`src/assay/`) — the **measurement** face: an honest number in a signed
  receipt (metrics, calibration, bootstrap intervals with an abstention floor, composites).
  Needs the science stack behind the `avow[assay]` extra. Wraps scikit-learn / scipy; it
  computes no metric math itself.
- **`writ`** (`src/writ/`) — the **effect** face: a policy-gated, atomically-attested
  privileged effect, sealed as a receipt on the same envelope.
- **`ts/`** — `@edgeproc/avow`, the byte-compatible TypeScript envelope. Pair-versioned
  with the Python `avow` (a test enforces `ts/package.json` version == `avow.__version__`).
- **`ts/packages/receipt-ui/`** — `@edgeproc/receipt-ui`, fail-closed React components that
  verify a receipt against a pinned key. Versioned **separately** from `@edgeproc/avow`.

Dependency arrows only ever point **into** `avow`: `assay → avow`, `writ → avow`. Avow
imports neither, so installing the envelope alone never pulls the scientific stack.

## The core ethos: deliver the guarantee you advertise

This repo's product IS verifiable trust, so every guard must be proven by **breaking the
property, not the form**. A test that stays green when you mutate the input (forge a
signature, recompute a hash, flip a bit) is measuring shape, not the guarantee. When you
fix a guard, write the adversarial red test first and watch it fail for the right reason.

## Local commands

- `uv run poe gate` — Python gate: ruff, `ruff format --check`, mypy `--strict`, xenon
  complexity A, pytest with statement **and** branch coverage against a 90% floor.
- `uv run poe gate-ts` — TypeScript gate (needs pnpm): biome, `tsc --noEmit`, vitest, build.
- `uv run poe gate-all` — both, mirroring CI's two jobs.
- `uv run python demo/run_demo.py` — the six measurement honesty cases.
- `uv run python demo/unification_demo.py` — one envelope + one verifier, both faces.

## Conventions

- **TDD, red-first.** Tests land with the code; a bug fix starts with a failing regression.
- **Grade A stays green:** functions stay small, mypy `--strict` passes, coverage floor holds.
- **Cross-language byte identity:** `testdata/vectors/` is replayed by both Python and the
  TypeScript `@edgeproc/avow`. Changing the *envelope* (canonical bytes, signature shape)
  means regenerating vectors (`uv run python tests/gen_vectors.py`) and keeping both sides
  byte-identical. Subject models like `assay.ReceiptPayload` are NOT in the vectors.
- **Versioning:** `src/avow/_version.py` is the single source of truth; bump
  `ts/package.json` to match (the parity test enforces it). A `v*` tag fans out to PyPI and
  npm token-free via OIDC — never hand-publish, never tag at an unchanged version.
- **CI/workflows:** every `uses:` is pinned to a full commit SHA (a test enforces this).
  Never weaken a supply-chain gate to make CI green.
- **Public surface, plain language:** no internal jargon in READMEs, package descriptions,
  or workflow comments. Lead with the *why*; define any term in one line.
