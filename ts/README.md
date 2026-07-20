# `@edgeproc/avow`

**The browser side of the Avow signed-receipt envelope.** It turns a small JSON
object (a "subject") into a tamper-evident receipt you can hand to anyone, and
lets them check it offline with just a public key. A receipt signed by the Python
`avow` kernel verifies here in the browser, and a receipt signed here verifies in
Python — **byte-for-byte, guaranteed by a shared conformance test**, not by hope.

Two moving parts, both boring on purpose:

- **Canonical bytes (RFC 8785 / JCS):** any two JSON objects that are *equal*
  serialize to the *same* bytes (keys sorted, numbers in one canonical form). So
  a receipt's hash is stable no matter who built the object or in what order.
- **Ed25519 sign/verify:** a detached signature over those canonical bytes,
  checked against a **pinned** public key you trust out-of-band.

## Why the cross-language guarantee matters

The score (or decision) is often computed in one language and checked in another:
Python computes it server-side, the browser verifies it; or the browser makes the
call and a Python CLI audits it later. That only works if *both* sides agree on
the exact bytes down to how `1e21` and `-0.0` are written. This package is kept
in lock-step with the Python kernel by replaying Python-generated golden vectors
(`testdata/vectors/*.json`) in CI: identical canonical bytes, identical
`sha256:` hashes, and Python-signed receipts that must verify here. If a single
byte ever diverges, the test — not production — goes red.

## Install

```bash
pnpm add @edgeproc/avow
```

Peer runtime: any modern browser or Node ≥ 22 (uses WebCrypto + `@noble/ed25519`).

## Quickstart — verify a receipt in 10 lines

```ts
import { verifySignature, type SignedReceipt } from "@edgeproc/avow";

// The signer's public key, pinned out-of-band (published on your site, in your
// bundle manifest, etc.). Never trust the key carried inside the receipt alone.
const PUBLISHER_KEY = "8a88e3dd7409f195fd52db2d3cba5d72ca6709bf1d94121bf3748801b40f6f5c";

async function check(receipt: SignedReceipt<{ kind: string; score: number }>) {
  await verifySignature(receipt, PUBLISHER_KEY); // throws on any tampering
  console.log("receipt is authentic:", receipt.payload);
}
```

`verifySignature` **fails closed**. It throws a coded error and never returns a
boolean you might forget to check:

- `ReplayMismatch` (`avow.replay_mismatch`) — the payload was altered after
  signing (its recomputed hash no longer matches).
- `SignatureInvalid` (`avow.signature_invalid`) — the receipt's embedded key is
  not the pinned key, or the signature doesn't verify.

The order mirrors the Python kernel exactly: recompute the hash, then reject any
receipt whose embedded `public_key` isn't the pinned one (that field lives
outside the signed bytes, so a re-signed forgery can swap it in), then verify the
Ed25519 signature under the pinned key.

## Signing (when the browser is the one making the decision)

```ts
import { signPayload, generateSeedHex } from "@edgeproc/avow";

const seedHex = generateSeedHex();       // 32-byte Ed25519 seed, keep it secret
const receipt = await signPayload(
  { kind: "score", score: 0.5, tags: ["a", "b"] },
  seedHex,
);
// receipt = { payload, payload_hash: "sha256:…", public_key, signature }
```

The subject must be a plain JSON value. The signed content is a pure function of
it (no timestamps), so identical subjects yield an identical signature — that
determinism is what makes cross-language byte-identity possible.

### Browser key custody (honest caveat)

A per-installation seed generated in the browser and stored in OPFS/IndexedDB is
**same-origin-readable** — any script on the same origin can read it. This is the
same capability-holding caveat the Python effect-face states: the receipt proves
*this installation* signed the decision, not that a hardware-protected key did.
No custody overclaim.

## Who signs vs who verifies

| Consumer         | Signs                          | Verifies            |
| ---------------- | ------------------------------ | ------------------- |
| AlmaMesh         | Python kernel (in Pyodide)     | same                |
| AML-Filter       | **TS** (per-installation key)  | TS                  |
| EdgeReco         | Python (backend, at build)     | TS (browser) + Py   |
| Personal-Finances| Python (localhost)             | Python CLI          |
| Privacy-Core     | TS (egress approval)           | TS                  |

## API

- `canonicalBytes(payload): Uint8Array` — RFC 8785 JCS bytes.
- `contentHash(payload): Promise<string>` — `"sha256:<hex>"` over those bytes.
- `signPayload(payload, seedHex): Promise<SignedReceipt>`.
- `verifySignature(receipt, expectedPublicKey): Promise<void>` — fail-closed.
- `generateSeedHex(): string`, `publicKeyHex(seedHex): Promise<string>`.
- Errors: `AvowError`, `CanonicalizationFailed`, `ReplayMismatch`,
  `SignatureInvalid` — each with a stable `.code`.

## Develop

```bash
pnpm install
pnpm gate        # lint (biome) + typecheck (tsc strict) + test (vitest) + build
```

The conformance suite (`src/canonical.test.ts`, `src/receipt.test.ts`) replays
the Python golden vectors — that suite *is* the cross-language contract.
