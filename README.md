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
score in a **signed receipt** that carries the inputs' content hash, the
metric/rubric version, the uncertainty interval, the calibration evidence, and an
Ed25519 signature. Anyone can re-run the receipt and confirm the number — and
verification fails if a single byte was tampered.

**The trust boundary, stated honestly.** A receipt proves *payload integrity under
some signer*: the content hash and signature detect any tampering of the signed
payload. It does **not**, on its own, prove *authenticity* — the signer's public
key rides in the receipt outside the signed payload, so an attacker can re-sign a
forged payload with their own key. Authenticity therefore requires **pinning the
signer's public key out-of-band**: you pass the key you trust (the `.pub` file from
`keygen`) to `verify`, and Assay rejects any receipt not signed by exactly that
key. Never trust the key embedded in the receipt.

v0 is **fully deterministic**: no LLM calls. (LLM-as-judge is v1.) All metric,
statistics, calibration, and crypto math is **reused** from `scikit-learn`,
`scipy`, `rfc8785` (RFC 8785 JCS), and `PyNaCl` — Assay only writes the trust,
honesty, and composition layer on top.

## Quickstart (copy-paste)

```bash
uv sync
uv run python demo/run_demo.py          # proves all 6 acceptance cases
uv run python demo/unification_demo.py  # ONE envelope + ONE verifier, BOTH faces

# or drive the CLI:
uv run assay keygen --out signing.key                 # also writes signing.key.pub
echo '{"metric":"binary","metric_version":"1","y_true":[0,1,0,1],"y_score":[0.2,0.8,0.3,0.7]}' > req.json
uv run assay score --request req.json --key signing.key --out receipt.json --ledger ledger.jsonl
uv run assay verify --receipt receipt.json --public-key signing.key.pub   # -> OK: receipt verified
```

The Python API mirrors the CLI:

```python
from nacl.signing import SigningKey

from assay import score, verify
from assay.models import ScoreRequest
from assay.settings import AssaySettings

signing_key = SigningKey.generate()
expected_public_key = bytes(signing_key.verify_key).hex()   # pin this out-of-band

request = ScoreRequest(
    metric="binary",
    metric_version="1",
    y_true=(0, 1, 0, 1),
    y_score=(0.2, 0.8, 0.3, 0.7),
)
receipt = score(request, signing_key=signing_key, settings=AssaySettings())
print(receipt.payload.score)         # calibrated point — or None when the sample is too thin
print(receipt.payload.interval_low, receipt.payload.interval_high)
# Verify against the PINNED signer key, never the receipt's own embedded key:
assert verify(receipt, expected_public_key=expected_public_key) is True
```

## Under the hood (for developers)

Assay is a thin **trust + honesty + composition layer** over reused libraries — it
computes no metric math itself:

- **Metrics** (`assay.metrics`): scikit-learn (`precision_recall_fscore_support`,
  `average_precision_score`, `roc_auc_score`, `accuracy_score`). F1, precision and
  recall are first-class in the receipt, not just headline accuracy.
- **Calibration** (`assay.calibration`): `sklearn.calibration.calibration_curve` +
  `brier_score_loss`, with a population-weighted **ECE** (Expected Calibration
  Error — the average gap between predicted confidence and observed frequency).
- **Uncertainty** (`assay.uncertainty`): `scipy.stats.bootstrap` percentile
  interval, with a **sample-size floor**: below it, Assay abstains rather than
  emit a point estimate.
- **Composite** (`assay.composite`): normalize multi-scale sub-scores to [0,1] and
  combine as a positive-weighted mean with an exact propagated interval.
- **Receipt** (`assay.receipt`): the signed content is canonicalized with **RFC 8785
  (JCS)** — a byte-stable JSON form — hashed with SHA-256, and signed with
  **Ed25519** (`PyNaCl`). The payload carries **no timestamp**, so identical inputs
  yield an identical, reproducible, offline-verifiable receipt.

**Signing-key custody:** `assay keygen` writes a 32-byte Ed25519 seed to a `0600`
file and its public key to a companion `.pub` file. Keys are never logged and never
committed (`*.key` is gitignored). The public key also travels inside each receipt
for convenience, but that embedded copy is **not** the trust anchor — a verifier
must pin the signer's public key it obtained out-of-band (the `.pub` file) and pass
it to `verify`. Only the private seed must be protected.

**One trust envelope, two faces (the moat).** `sign_payload` / `verify_signature` /
`payload_digest` operate only on the canonical JSON of a frozen *subject* model, so
they are agnostic to what that subject carries. The *score* face signs a `ReceiptPayload`
(what a number is). The *effect* face — **Writ** (`assay.writ`) — signs an `EffectSubject`
(what an effect did) through the **same** envelope, with the trust boundary (`assay.receipt`)
unchanged. One `verify_receipt(..., expected_public_key=...)` verifies both:
`demo/unification_demo.py` produces a score receipt and two effect receipts (allow + deny)
and verifies all three under one pinned key.

**Governed effect.** `writ.gate(request, policy, effector)` evaluates a typed policy: on
**deny** it signs a denial receipt and never runs the effect; on **allow** the effector
runs the effect, then signs an effect receipt — both verifiable through the shared envelope.
The v0 policy decider is a Python predicate (`Allowlist`); **OPA/Rego is the v1 decider**.

**Un-bypassable seam — stated honestly.** The effect credential and the privileged effect
live only inside the effector, which `governed_gate` captures in the single closure the
agent receives; the effector itself is never handed over, so the only path to the effect is
through the guard. This is the **v0 capability-holding approximation**: the credential is
still in-process, so same-process reflection could reach it. TRUE un-bypassable enforcement
(a separate-process broker or a WASM guest, where the agent's address space cannot reach the
credential) is the **v1 hardening**. We do not claim more than that.

See `docs/ARCHITECTURE.md` for the data-flow diagram and `docs/superpowers/plans/`
for the full TDD build record.

## Status

v0 shipped — deterministic (no LLM), full test pyramid green under `uv run poe gate`
(ruff, mypy `--strict`, xenon A, 100% coverage). See the execution-ready TDD plan:
[`docs/superpowers/plans/2026-07-19-assay-v0.md`](docs/superpowers/plans/2026-07-19-assay-v0.md).

## License

MIT © Harish Seshadri
