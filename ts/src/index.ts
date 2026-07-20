/**
 * `@edgeproc/avow` — the browser side of the Avow signed-receipt envelope.
 *
 * RFC-8785 canonical bytes + Ed25519 sign/verify, kept byte-compatible with the
 * Python `avow` kernel by a shared golden-vector conformance suite. A receipt
 * signed in Python verifies here; a receipt signed here verifies in Python.
 */

export { canonicalBytes, contentHash, type JsonValue } from "./canonical.js";
export {
  AvowError,
  CanonicalizationFailed,
  ReplayMismatch,
  SignatureInvalid,
} from "./errors.js";
export { generateSeedHex, publicKeyHex } from "./keys.js";
export { type SignedReceipt, signPayload, verifySignature } from "./receipt.js";
