# QUICKSTART

1. `uv sync`
2. `uv run python demo/run_demo.py` — proves all six acceptance cases.
3. `uv run poe gate` — lint, mypy `--strict`, xenon A, tests (100% coverage).

CLI: `uv run assay --help`.

```bash
uv run assay keygen --out signing.key                 # also writes signing.key.pub
echo '{"metric":"binary","metric_version":"1","y_true":[0,1,0,1],"y_score":[0.2,0.8,0.3,0.7]}' > req.json
uv run assay score --request req.json --key signing.key --out receipt.json --ledger ledger.jsonl
uv run assay verify --receipt receipt.json --public-key signing.key.pub   # -> OK: receipt verified
```
