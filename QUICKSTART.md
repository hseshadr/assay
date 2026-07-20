# QUICKSTART

One distribution `avow`, three import packages: `avow` (envelope), `assay` (scoring),
`writ` (effect). `assay` and `writ` import `avow`; `avow` imports neither.

1. `uv sync --all-extras` — installs all three faces + the CLI + tooling for dev.
2. `uv run python demo/run_demo.py` — scoring face: six honesty acceptance cases.
3. `uv run python demo/unification_demo.py` — one envelope + one verifier, both faces.
4. `uv run poe gate` — ruff, ruff-format, mypy `--strict`, xenon A, tests (100% coverage).

Install matrix (for consumers):

| Command | Gives you |
|---|---|
| `pip install avow` | `import avow`, `import writ` |
| `pip install 'avow[assay]'` | `+ import assay` (scoring) |
| `pip install 'avow[cli]'` | `+ the assay CLI` |

CLI: `uv run assay --help`.

```bash
uv run assay keygen --out signing.key                 # also writes signing.key.pub
echo '{"metric":"binary","metric_version":"1","y_true":[0,1,0,1],"y_score":[0.2,0.8,0.3,0.7]}' > req.json
uv run assay score --request req.json --key signing.key --out receipt.json --ledger ledger.jsonl
uv run assay verify --receipt receipt.json --public-key signing.key.pub   # -> OK: receipt verified
```

Regenerate the cross-language golden vectors after any canonicalization change:

```bash
uv run python tests/gen_vectors.py    # writes testdata/vectors/{canonical,receipts}.json
```
