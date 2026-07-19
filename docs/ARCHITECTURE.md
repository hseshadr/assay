# Assay architecture

One-way data flow: a request is computed into a deterministic payload, the payload
is canonicalized and hashed, the hash is Ed25519-signed into a receipt, and the
receipt is (optionally) appended to a ledger and verified offline.

```d2
request: ScoreRequest / CompositeRequest
compute: "metrics · calibration · uncertainty · composite (reused libs)"
payload: ReceiptPayload (deterministic, no timestamp)
hash: canonical.py (RFC 8785 JCS -> sha256)
sign: receipt.py (Ed25519 / PyNaCl)
receipt: ScoreReceipt
ledger: ledger.py (append-only JSONL)
verify: verify.py (offline: recompute hash + check signature)

request -> compute -> payload -> hash -> sign -> receipt
receipt -> ledger
receipt -> verify
```

Every arrow is one-directional. Honesty invariants:

1. **No timestamp in the signed payload** → the receipt hash is a pure function of
   the inputs, so it reproduces byte-for-byte.
2. **Sample-size floor** → below it, Assay abstains instead of emitting a fabricated
   point estimate.
3. **Fail-closed verification, with a pinned signer** → any tampered byte (payload
   or signature) is detectable offline, with no network and no original inputs.
   But integrity is not authenticity: a receipt only proves *payload integrity
   under some signer*, because the `public_key` field rides outside the signed
   payload and an attacker can re-sign a forged payload with their own key. So
   `verify` takes an `expected_public_key` that the caller pins **out-of-band**
   (the `.pub` file from `keygen`) and rejects any receipt not signed by exactly
   that key — the receipt's own embedded key is never trusted.

## One trust envelope, two faces (score + effect)

`sign_payload` / `verify_signature` / `payload_digest` sign and check the canonical
JSON of a frozen *subject* — they never inspect its fields. `ReceiptPayload` is the
*score* face's subject. The *effect* face — **Writ** (`assay.writ`) — defines its own
frozen `EffectSubject` and reuses this same hash-sign-verify envelope unchanged; only
the subject differs, never the trust boundary. `verify_receipt` is generic over the
subject, so one public verifier serves both faces (`demo/unification_demo.py`).

### The governed effect gate

```d2
request: EffectRequest (action, target, args_digest)
policy: "Policy.permits() — typed predicate (v1: OPA/Rego)"
gate: "writ.gate — branch on the decision"
effect: "effector.run — privileged side-effect (ALLOW only)"
seal: "effector.seal — sign EffectSubject (ALWAYS)"
receipt: EffectReceipt = SignedReceipt[EffectSubject]

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
