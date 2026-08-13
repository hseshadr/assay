# QUICKSTART

New here? Read [`README.md`](README.md) first — it explains what a receipt is and why it
matters. This page is the shortest path from clone to a verified receipt.

Before production use, read the [operational contract](docs/OPERATIONS.md) for the
privacy, plaintext retention, key/head custody, recovery, and performance boundaries.

**Requires Python 3.13+.** The distribution is named `avow`; the command it installs is
named **`assay`**. There is no `avow` command.

One distribution `avow`, three import packages: `avow` (envelope), `assay` (scoring),
`writ` (effect). `assay` and `writ` import `avow`; `avow` imports neither.

```bash
git clone https://github.com/hseshadr/assay.git
cd assay
```

1. `uv sync --all-extras` — installs all three faces + the CLI + tooling for dev.
2. `uv run python demo/run_demo.py` — scoring face: six honesty acceptance cases.
3. `uv run python demo/unification_demo.py` — one envelope + one verifier, both faces.
4. `uv run poe gate` — Python: ruff, ruff-format, mypy `--strict`, xenon A, tests.
5. `uv run poe gate-ts` — TypeScript: biome, `tsc --noEmit`, vitest, build (needs pnpm).
   `uv run poe gate-all` runs both, mirroring CI's two jobs.

Install matrix (for consumers):

| Command | Gives you |
|---|---|
| `pip install avow` | `import avow`, `import writ` |
| `pip install 'avow[assay]'` | `+ import assay` (scoring) |
| `pip install 'avow[cli]'` | + the `assay` command |

CLI: `uv run assay --help`.

```bash
uv run assay keygen --out signing.key                 # also writes signing.key.pub
echo '{"metric":"binary","metric_version":"1","y_true":[0,1,0,1],"y_score":[0.2,0.8,0.3,0.7]}' > req.json
uv run assay score --request req.json --key signing.key --out receipt.json --ledger ledger.jsonl
uv run assay verify --receipt receipt.json --public-key signing.key.pub   # -> OK: receipt verified
uv run assay verify-ledger --ledger ledger.jsonl --public-key signing.key.pub --head ledger.jsonl.head   # -> OK: ledger verified, 1 entry intact
```

`keygen` wrote `signing.key.pub` and `score` wrote `ledger.jsonl.head`, so a cold clone
already has both pins `verify-ledger` needs: the public key (*who* signed the entries) and
the chain head (*which* entries there are). Copy the head somewhere the ledger's writer
cannot reach — beside the ledger it is a convenience, not a control.

The **chained, keyed** `verify-ledger` shown above ships in the current published 0.4.0.
The prepared 0.4.1 patch supersedes 0.4.0 for CLI ledger writers by holding one bounded
process lock across the append and convenience-head save. Until 0.4.1 is published,
installing from PyPI still gives 0.4.0; see [`CHANGELOG.md`](CHANGELOG.md).

Pointed at a path it cannot read, `verify-ledger` fails closed with
`avow.ledger_unreadable` rather than reporting zero entries intact. With no head to check
against, it fails closed with `avow.ledger_head_unreadable`.

Regenerate the cross-language golden vectors after any canonicalization change:

```bash
uv run python tests/gen_vectors.py    # writes testdata/vectors/{canonical,receipts}.json
```
