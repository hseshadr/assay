# Assay

**The scoring engine that refuses to lie.**

Assay computes ML and evaluation scores and hands them back **calibrated,
uncertainty-aware, reproducible, and cryptographically signed** — and it never
fabricates precision. If the sample is too thin to justify a point estimate,
Assay widens the interval or abstains instead of inventing a confident number.

## Why it exists

A raw metric — `f1 = 0.83` — is a claim with no receipt. You cannot tell whether
it was computed on 12 examples or 12,000, whether the probabilities were
calibrated, or whether the number will reproduce tomorrow. Assay wraps every
score in a **signed, offline-verifiable receipt** that carries the inputs'
content hash, the metric/rubric version, the uncertainty interval, the
calibration evidence, and an Ed25519 signature. Anyone can re-run the receipt and
confirm the number — or watch verification fail if a single byte was tampered.

v0 is **fully deterministic**: no LLM calls. (LLM-as-judge is v1.) All metric,
statistics, calibration, and crypto math is **reused** from `scikit-learn`,
`scipy`, `rfc8785` (RFC 8785 JCS), and `PyNaCl` — Assay only writes the trust,
honesty, and composition layer on top.

## Quickstart

> Placeholder — the API below is the target contract from the v0 TDD plan
> (`docs/superpowers/plans/2026-07-19-assay-v0.md`); it lands as the plan is
> executed.

```bash
git clone https://github.com/hseshadr/assay.git
cd assay
uv sync
uv run poe gate        # lint + format + mypy --strict + complexity + tests
```

```python
from assay import score, verify

receipt = score(
    metric="f1",
    y_true=[1, 0, 1, 1, 0],
    y_pred=[1, 0, 1, 0, 0],
    signing_key=key,
)
print(receipt.value)          # calibrated point estimate
print(receipt.interval)       # (low, high) — widened / abstained when sample is thin
assert verify(receipt)        # signature valid AND score recomputes identically
```

## Status

Green-baseline scaffold. See the execution-ready TDD plan:
[`docs/superpowers/plans/2026-07-19-assay-v0.md`](docs/superpowers/plans/2026-07-19-assay-v0.md).

## License

MIT © Harish Seshadri
