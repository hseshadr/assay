# Avow

**The trust kernel: one signed receipt, three Legos.**

Avow turns a claim into a **receipt you can check** — a small, signed record that
proves *exactly what was claimed* and fails loudly if a single byte is changed. It
ships as one installable distribution (`avow`) that exposes three import packages you
can pick and choose:

| Package | It is… | Depends on | Install |
|---|---|---|---|
| **`avow`** | the shared **envelope** — sign, hash, verify a receipt | pydantic, pynacl, rfc8785 | `pip install avow` |
| **`assay`** | the **scoring** face — an honest number, wrapped in a receipt | `avow` + scikit-learn/scipy/numpy | `pip install 'avow[assay]'` |
| **`writ`** | the **effect** face — a policy-gated action, sealed as a receipt | `avow` only | `pip install avow` |

The command-line tool lives behind `pip install 'avow[cli]'`.

> **One rule you can hold in your head:** the envelope signs the *canonical bytes of a
> frozen subject* and never looks inside. So the exact same sign/verify code carries a
> score for the scoring face and an action for the effect face. One envelope, many
> subjects. The dependency arrows only ever point **into** `avow` — `assay → avow` and
> `writ → avow`; `avow` imports neither, which is why installing the envelope alone
> never pulls the heavy science stack.

## Why it exists

A raw claim — `f1 = 0.83`, or "I deleted account 7" — is a statement with no receipt.
You cannot tell whether the score ran on 12 examples or 12,000, or whether the action
was actually allowed. Avow wraps the claim in a **signed receipt** carrying the inputs'
content hash and an Ed25519 signature. Anyone holding the receipt can re-check it
offline — and verification fails if anything was tampered.

**The trust boundary, stated honestly.** A receipt proves *payload integrity under some
signer*. It does **not**, on its own, prove *authenticity* — the signer's public key
rides in the receipt outside the signed bytes, so an attacker can re-sign a forged
payload with their own key. Authenticity therefore requires **pinning the signer's
public key out-of-band**: you pass the key you already trust (the `.pub` from `keygen`)
to `verify`, and Avow rejects any receipt not signed by exactly that key. Never trust
the key embedded in the receipt.

## Quickstart (copy-paste)

```bash
# dev setup (this repo installs all faces + tooling):
uv sync --all-extras
uv run poe gate                          # ruff · ruff-format · mypy --strict · xenon A · pytest (100%)
uv run python demo/run_demo.py           # scoring face: 6 honesty acceptance cases
uv run python demo/unification_demo.py   # ONE envelope + ONE verifier, BOTH faces
```

**Envelope only** — sign and verify any frozen subject (base install, no science stack):

```python
from pydantic import BaseModel, ConfigDict
from avow import generate_signing_key, public_key_hex, sign_payload, verify_signature

class Claim(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    what: str
    value: float

key = generate_signing_key()
pinned = public_key_hex(key)                 # pin this out-of-band
receipt = sign_payload(Claim(what="f1", value=0.83), key)
verify_signature(receipt, expected_public_key=pinned)   # raises on any tamper
```

**Scoring face** (`pip install 'avow[assay]'`) — an honest number in a receipt:

```python
from avow import generate_signing_key, public_key_hex
from assay import score, verify
from assay.models import ScoreRequest
from assay.settings import AssaySettings

key = generate_signing_key()
request = ScoreRequest(metric="binary", metric_version="1",
                       y_true=(0, 1, 0, 1), y_score=(0.2, 0.8, 0.3, 0.7))
receipt = score(request, signing_key=key, settings=AssaySettings())
print(receipt.payload.score)   # calibrated point — or None when the sample is too thin
assert verify(receipt, expected_public_key=public_key_hex(key)) is True
```

**Effect face** (`writ`, base install) — a policy-gated, sealed action:

```python
from avow import generate_signing_key, public_key_hex, verify_signature
from writ import Allowlist, EffectRequest, KeyholderEffector, governed_gate

key = generate_signing_key()
def do_it(_req: EffectRequest) -> None: ...          # the privileged effect
gate = governed_gate(Allowlist(frozenset({"read"})),
                     KeyholderEffector(effect=do_it, signing_key=key))
receipt = gate(EffectRequest(action="read", target="ledger-7", args_digest="sha256:abc"))
verify_signature(receipt, expected_public_key=public_key_hex(key))
print(receipt.payload.decision)                       # "allow" — or "deny", still sealed
```

**CLI** (`pip install 'avow[cli]'`):

```bash
uv run assay keygen --out signing.key                 # also writes signing.key.pub
echo '{"metric":"binary","metric_version":"1","y_true":[0,1,0,1],"y_score":[0.2,0.8,0.3,0.7]}' > req.json
uv run assay score --request req.json --key signing.key --out receipt.json --ledger ledger.jsonl
uv run assay verify --receipt receipt.json --public-key signing.key.pub   # -> OK: receipt verified
```

## Under the hood (for developers)

**`avow` — the envelope.** `sign_payload` / `verify_signature` / `payload_digest`
operate only on the canonical JSON of a frozen `SignedReceipt[SubjectT]` subject.
Canonicalization is **RFC 8785 (JCS)** — a byte-stable JSON form — hashed with SHA-256
and signed with **Ed25519** (`PyNaCl`). Payloads carry **no timestamp**, so identical
inputs yield an identical, reproducible, offline-verifiable receipt. `avow.ledger` is an
append-only, content-addressed JSONL log with a fail-closed integrity check, generic
over the subject. Coded failures live in `avow.errors` (`avow.*` codes under `AvowError`).

**`assay` — the scoring face.** A thin trust + honesty + composition layer over reused
libraries (it computes no metric math itself): scikit-learn for precision/recall/F1,
PR-AUC, ROC-AUC and Brier; `scipy.stats.bootstrap` for percentile intervals with a
**sample-size floor** (below it, Assay abstains rather than invent a point estimate);
population-weighted **ECE** for calibration; a positive-weighted composite with a
propagated interval. `assay.receipt` defines the score subjects; the envelope signs
them. Its errors are `assay.*` under `AssayError`. Import `assay` without the
`[assay]` extra and you get a coded `ScoringExtraMissing`, never a raw traceback.

**`writ` — the effect face.** `writ.gate(request, policy, effector)` evaluates a typed
policy: on **deny** it seals a signed denial receipt and never runs the effect; on
**allow** the effector runs the effect, then seals a signed effect receipt — both
verifiable through the shared envelope. The v0 policy decider is a Python predicate
(`Allowlist`); **OPA/Rego is the v1 decider**.

**Un-bypassable seam — stated honestly.** The effect credential and the privileged
effect live only inside the effector, which `governed_gate` captures in the single
closure the agent receives; the effector itself is never handed over, so the only path
to the effect is through the guard. This is the **v0 capability-holding approximation**:
the credential is still in-process, so same-process reflection could reach it. TRUE
un-bypassable enforcement (a separate-process broker or a WASM guest, where the agent's
address space cannot reach the credential) is the **v1 hardening**. We claim no more.

**Signing-key custody.** `assay keygen` (and `avow.keys`) write a 32-byte Ed25519 seed
to a `0600` file and the public key to a companion `.pub`. Keys are never logged and
never committed (`*.key` is gitignored). The public key also travels inside each receipt
for convenience, but that embedded copy is **not** the trust anchor — a verifier pins
the out-of-band key and passes it to `verify`.

**Cross-language byte identity.** `testdata/vectors/` holds golden vectors generated by
`tests/gen_vectors.py` (canonical bytes + hashes, and receipts signed with a fixed
non-secret test seed). The Python suite replays them in `tests/test_vectors.py`; a
future TypeScript `@edgeproc/avow` replays the *same files* byte-for-byte, so any RFC
8785 number-serialization divergence fails in CI, not in production.

See [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) for the data-flow diagram, the
import edges, and the native-vs-browser story.

## Status

v0 shipped — deterministic (no LLM). Full pyramid green under `uv run poe gate`
(ruff, ruff-format, mypy `--strict`, xenon A, 100% coverage). CI mirrors the gate.

## License

MIT © Harish Seshadri
