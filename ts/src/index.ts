/**
 * `@edgeproc/avow` — the browser side of the Avow trust kernel.
 *
 * Two faces, mirroring the Python distribution of the same name:
 *
 * - **The envelope.** RFC-8785 canonical bytes + Ed25519 sign/verify, kept
 *   byte-compatible with the Python `avow` kernel by a shared golden-vector
 *   conformance suite. A receipt signed in Python verifies here; a receipt signed
 *   here verifies in Python.
 * - **The metrics.** Ranked-retrieval and binary-classification metrics, kept
 *   answer-compatible with the Python `assay` face by a second shared vector file.
 *   A recall@10 measured in a browser is the number the server would have printed.
 */

export { canonicalBytes, contentHash, type JsonValue } from "./canonical.js";
export {
  AvowError,
  CanonicalizationFailed,
  PayloadHashMismatch,
  ReplayMismatch,
  SignatureBytesInvalid,
  SignatureInvalid,
  SignerMismatch,
} from "./errors.js";
export { generateSeedHex, publicKeyHex } from "./keys.js";
export {
  type BinaryRates,
  binaryRates,
  type ConfusionCounts,
  confusionCounts,
  DEFAULT_THRESHOLD,
  ratesFromCounts,
  type ThresholdOptions,
} from "./metrics.js";
export {
  binaryJudgments,
  f1AtK,
  type Judgments,
  mrr,
  precisionAtK,
  recallAtK,
} from "./ranking.js";
export { type SignedReceipt, signPayload, verifySignature } from "./receipt.js";
export {
  AssayError,
  EmptyRelevantSet,
  InvalidRankingRequest,
  InvalidScoreRequest,
} from "./scoringErrors.js";
