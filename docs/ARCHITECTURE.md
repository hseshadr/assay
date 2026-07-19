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
3. **Fail-closed verification** → any tampered byte (payload or signature) is
   detectable offline, with no network and no original inputs.

## The trust envelope is unification-ready

`sign_payload` / `verify_signature` / `payload_digest` sign and check the canonical
JSON of a frozen *subject* — they never inspect its fields. `ReceiptPayload` is the
*score* face's subject. A future *effect* face ("Writ") would define its own frozen
subject model and reuse this same hash-sign-verify envelope unchanged; only the
subject differs, never the trust boundary.
