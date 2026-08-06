# `@edgeproc/avow`

**The browser side of the Avow trust kernel: signed receipts, and the metrics that
go inside them.** Two faces, both kept in lock-step with the Python package of the
same name by shared golden vectors — not by hope.

- **The envelope.** Turn a small JSON object (a "subject") into a tamper-evident
  receipt anyone can check offline with just a public key. A receipt signed by the
  Python `avow` kernel verifies here, and one signed here verifies in Python,
  byte-for-byte.
- **The metrics** (new in 0.4.0). recall@k, precision@k, F1@k, MRR, and the binary
  confusion set — the same answers the Python `assay` face computes, pinned case by
  case. See [Metrics](#metrics-recallk-mrr-and-the-confusion-set).

## The envelope

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
// (Inert placeholder shown — substitute the 64-hex key you actually pinned.)
const PUBLISHER_KEY = "deadbeefdeadbeefdeadbeefdeadbeefdeadbeefdeadbeefdeadbeefdeadbeef";

async function check(receipt: SignedReceipt<{ kind: string; score: number }>) {
  await verifySignature(receipt, PUBLISHER_KEY); // throws on any tampering
  console.log("receipt is authentic:", receipt.payload);
}
```

`verifySignature` **fails closed**. It throws a coded error and never returns a
boolean you might forget to check:

- `PayloadHashMismatch` (`avow.payload_hash_mismatch`) — the payload was altered
  after signing (its recomputed hash no longer matches). Called `ReplayMismatch`
  through 0.2.0; renamed in 0.3.0 because it never detected replay.
- `SignerMismatch` (`avow.signer_mismatch`) — the receipt's embedded key is not
  the pinned key: signed by someone you don't trust, a **provenance** failure.
  The signature is never even checked.
- `SignatureBytesInvalid` (`avow.signature_invalid`) — the signer matched but the
  signature doesn't verify: a **tamper** failure.

The last two both extend `SignatureInvalid`, so `instanceof SignatureInvalid`
still catches either if you don't need to tell them apart. These are the same
codes the Python kernel raises for the same two cases.

The order mirrors the Python kernel exactly: recompute the hash, then reject any
receipt whose embedded `public_key` isn't the pinned one (that field lives
outside the signed bytes, so a re-signed forgery can swap it in), then verify the
Ed25519 signature under the pinned key.

### What verification does not prove: freshness

`verifySignature` proves **who signed it** and **that it is unmodified**. It does
**not** prove that this is the first time the receipt has been presented, or that
it was made recently.

A replayed receipt — a genuine one, captured by anyone who saw it and handed over
again unchanged — is byte-identical to the original and verifies forever. That is
not a gap to close inside the envelope: a signature binds content to a *signer*,
it cannot bind it to an *occasion*, and the determinism that lets a receipt
re-verify offline years later is exactly what lets it be re-presented.

**This package ships the envelope only — there is no ledger in the browser
build.** So if your threat model includes "someone shows me an old receipt as if
it were new", you must hold that state yourself: carry a nonce or request-id
inside your own subject before signing and track the ones you have accepted, or
record entries server-side in the Python `avow.ledger`, whose hash chain rejects a
replayed entry against a pinned head.

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

## Metrics: recall@k, MRR, and the confusion set

**The problem this solves:** a browser that measures its own search quality had no
choice but to hand-roll the arithmetic, because there was nothing to import. Then
the number the release gate reads is one nobody has checked against a reference.

```ts
import { recallAtK, mrr, binaryJudgments } from "@edgeproc/avow";

// Which documents SHOULD have come back, and which ones did.
const relevant = binaryJudgments(["acme-corp", "acme-holdings"]);
const ranked = ["zeta-ltd", "acme-corp", "beta-inc"];

recallAtK(relevant, ranked, 3); // 0.5  — 1 of the 2 relevant ones reached the top 3
mrr(relevant, ranked);          // 0.5  — the first hit sits at position 2
```

```ts
import { binaryRates, confusionCounts } from "@edgeproc/avow";

const labels = [0, 0, 1, 1];
const scores = [0.1, 0.9, 0.2, 0.8];

confusionCounts(labels, scores); // { truePositives: 1, falsePositives: 1, … }
binaryRates(labels, scores).falseNegativeRate; // 0.5 — the miss rate
```

One-line definitions, since none of these terms carry themselves:

| Metric         | Reads as                                                       |
| -------------- | -------------------------------------------------------------- |
| `precisionAtK` | of the top k positions, what fraction held a relevant document  |
| `recallAtK`    | of everything relevant, what fraction reached the top k         |
| `f1AtK`        | the harmonic mean of those two                                  |
| `mrr`          | 1 / (position of the first relevant hit)                        |
| `confusionCounts` | the four cells: TP / FP / TN / FN at a decision threshold    |
| `binaryRates`  | accuracy, precision, recall, F1, FPR and FNR from those cells   |

**These are the same numbers Python prints.** `testdata/vectors/metrics.json` holds
23 hand-computed cases that *both* test suites replay — 7 ranking and 7 ranking
refusals, 5 classification and 4 classification refusals. Python reaches its answers
through `trec_eval` and scikit-learn; this package counts them out against the
definitions. If the two ever disagree, CI goes red in both languages.

**Everything refuses rather than guessing.** An empty ranked list, a duplicate
document, a fractional relevance grade, a `k` of 0, a set with nothing judged
relevant, a single-class label set — each throws a coded `AssayError`
(`assay.invalid_ranking_request`, `assay.empty_relevant_set`,
`assay.invalid_request`), with the same code Python raises. Recall of a set nobody
judged is not 0.0; it is a question with no answer, and saying so is more useful
than printing a number.

### What is deliberately missing

**nDCG@k and average precision / MAP are not here, and are not coming.** Both are
`trec_eval`'s, whose engine is a C++ binary with no npm binding, and both carry
conventions — how the ideal ranking is built over documents the ranker never
returned, how graded gains collapse to binary, where truncation applies — that
belong to that implementation rather than to any textbook. A version written from
the definition would produce a number that *looks* like Python's and is not, which
is worse than not shipping it. Python remains their only implementation.

**PR-AUC and ROC-AUC are missing for the same reason**: they integrate over every
threshold with scikit-learn's own tie-handling, and they are the two metrics on
Python's `binary_scores` that are not a ratio of confusion cells.

## API

**Envelope**

- `canonicalBytes(payload): Uint8Array` — RFC 8785 JCS bytes.
- `contentHash(payload): Promise<string>` — `"sha256:<hex>"` over those bytes.
- `signPayload(payload, seedHex): Promise<SignedReceipt>`.
- `verifySignature(receipt, expectedPublicKey): Promise<void>` — fail-closed.
- `generateSeedHex(): string`, `publicKeyHex(seedHex): Promise<string>`.
- Errors: `AvowError`, `CanonicalizationFailed`, `PayloadHashMismatch`,
  `SignatureInvalid` and its two subclasses `SignerMismatch` /
  `SignatureBytesInvalid` — each with a stable `.code`.

**Metrics**

- `precisionAtK(relevant, ranked, k)`, `recallAtK(...)`, `f1AtK(...)`,
  `mrr(relevant, ranked)` — all take `Judgments` (a `{docId: gain}` map; gain > 0
  means relevant) and an ordered array of document ids.
- `binaryJudgments(docIds): Judgments` — a relevant *set* as judgments.
- `confusionCounts(yTrue, yScore, { threshold })`, `binaryRates(...)`,
  `ratesFromCounts(counts)` — `DEFAULT_THRESHOLD` is `0.5`, and a score *equal* to
  the threshold is a positive prediction.
- Errors: `AssayError`, `InvalidRankingRequest`, `EmptyRelevantSet`,
  `InvalidScoreRequest` — each with a stable `.code` matching Python's.

## Develop

```bash
pnpm install
pnpm gate        # lint (biome) + typecheck (tsc strict) + test (vitest) + build
```

The conformance suites (`src/canonical.test.ts`, `src/receipt.test.ts`,
`src/metricVectors.test.ts`) replay the shared golden vectors — those suites *are*
the cross-language contract. `uv run poe mutants`, from the repository root, breaks
each guard in this package one at a time and requires the suite to go red.
