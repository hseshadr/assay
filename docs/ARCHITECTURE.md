# Avow architecture

One distribution (`avow`), three import packages, one dependency direction.

## The three packages and their import edges

`assay` (scoring) and `writ` (effect) both import the `avow` envelope; `avow` imports
neither. The arrows point one way only, which is what lets the envelope install without
the science stack.

```d2
direction: right
avow: "avow — the envelope\n(canonical · keys · envelope · verify · ledger · errors)"
assay: "assay — scoring face\n(metrics · calibration · uncertainty · composite · api · cli)"
writ: "writ — effect face\n(gate · policy · effector)"

assay -> avow: imports
writ -> avow: imports
```

**Enforced by construction** (and asserted in `tests/test_envelope_split.py`): importing
`avow` loads no `assay`, no `writ`, and no scikit-learn/scipy. Base deps are the
envelope's only — `pydantic`, `pydantic-settings`, `pynacl`, `rfc8785`.

### Install matrix

| Command | Import packages available | For |
|---|---|---|
| `pip install avow` | `avow`, `writ` | signing/verifying receipts; the effect gate |
| `pip install 'avow[assay]'` | `+ assay` | the scoring face (metrics, calibration, uncertainty, composite) |
| `pip install 'avow[cli]'` | `+ assay` CLI (`assay` script) | the command-line tool |

Import `assay` without the `[assay]` extra and it fails with a coded
`ScoringExtraMissing`, never a bare `ModuleNotFoundError`.

## Data flow (scoring face over the envelope)

A request is computed into a deterministic payload; the payload is canonicalized and
hashed; the hash is Ed25519-signed into a receipt; the receipt is (optionally) appended
to a ledger and verified offline.

```d2
request: ScoreRequest / CompositeRequest        # assay
compute: "metrics · calibration · uncertainty · composite (reused libs)"  # assay
payload: ReceiptPayload (deterministic, no timestamp)  # assay.receipt
hash: "avow.canonical (RFC 8785 JCS -> sha256)"
sign: "avow.envelope (Ed25519 / PyNaCl)"
receipt: "SignedReceipt[ReceiptPayload]"
ledger: "avow.ledger (append-only JSONL, generic)"
verify: "avow.verify (offline: recompute hash + pinned-key signature)"

request -> compute -> payload -> hash -> sign -> receipt
receipt -> ledger
receipt -> verify
```

Every arrow is one-directional. Honesty invariants:

1. **No timestamp in the signed payload** → the receipt hash is a pure function of the
   inputs, so it reproduces byte-for-byte.
2. **Sample-size floor** → below it, the scoring face abstains instead of emitting a
   fabricated point estimate.
3. **Fail-closed verification, with a pinned signer** → any tampered byte (payload or
   signature) is detectable offline, with no network and no original inputs. Integrity
   is not authenticity: the `public_key` field rides outside the signed payload, so
   `verify` takes an `expected_public_key` the caller pins **out-of-band** (the `.pub`
   from `keygen`) and rejects any receipt not signed by exactly that key.

## One trust envelope, two faces (score + effect)

`avow.sign_payload` / `verify_signature` / `payload_digest` sign and check the canonical
JSON of a frozen *subject* — they never inspect its fields. `assay.receipt.ReceiptPayload`
is the *score* face's subject. `writ` defines its own frozen `EffectSubject` and reuses
this same hash-sign-verify envelope unchanged; only the subject differs, never the trust
boundary. `avow.verify_receipt` is generic over the subject, so one public verifier
serves both faces (`demo/unification_demo.py`).

### The governed effect gate

```d2
request: EffectRequest (action, target, args_digest)
policy: "Policy.permits() — typed predicate (v1: OPA/Rego)"
gate: "writ.gate — branch on the decision"
effect: "effector.run — privileged side-effect (ALLOW only)"
seal: "effector.seal — sign EffectSubject (ALWAYS)"
receipt: "EffectReceipt = SignedReceipt[EffectSubject]"

request -> policy -> gate
gate -> effect: allow
gate -> seal
effect -> seal: allow
seal -> receipt
```

On **deny** the effect never runs and a signed denial receipt is sealed; on **allow**
the effector runs the effect, then seals a signed effect receipt. Both are verifiable
offline through the shared envelope under a pinned signer.

**Un-bypassable seam — honest v0.** The effect credential (the signing key) and the
privileged effect live only inside the `Effector`. `governed_gate(policy, effector)`
captures the effector in the single closure the agent receives; the effector is never
passed out, so the only path to the effect is back through the guard. This is a
**capability-holding approximation**: the credential is still in-process, reachable by
same-process reflection. TRUE un-bypassability — a **separate-process broker** or a
**WASM guest**, where the agent's address space cannot reach the credential — is the
**v1 hardening**. Even so, a bypass buys little: only the effector's held key can seal a
receipt that verifies under the pinned signer, so any forged effect fails verification.

## Native vs browser (the byte-identity contract)

The kernel is designed to run unmodified both on CPython and in the browser, with
cross-language byte identity **gated, not assumed**:

- **Native / CPython** consumers import the Python kernel directly.
- **Pyodide** consumers `micropip`-install the same pure-Python wheel; `pynacl`,
  `pydantic` and `pydantic-core` are in the official Pyodide lockfile and `rfc8785` is
  pure Python — so the actual Python envelope runs in-browser, no crypto rewrite.
- **Pure-TS** consumers use a sibling `@edgeproc/avow` package (RFC 8785 canonicalizer +
  Ed25519 sign/verify). It is kept byte-compatible by replaying the golden vectors in
  `testdata/vectors/` — the SAME files the Python suite replays. RFC 8785 number
  serialization (ECMAScript shortest round-trip) is the known hazard, so the vectors
  deliberately include `0.5`, `0.1`, `1e21`, `-0.0`, `1e-7`; any divergence fails in CI.

The TypeScript package `@edgeproc/avow` has already shipped — its source lives in this
repo at `ts/`, it is published on npm, and the `ts-gate` job in CI replays the vectors in
`testdata/vectors/` against it, so a cross-language divergence fails in CI, not
production.
