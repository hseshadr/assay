import type { JsonValue, SignedReceipt } from "@edgeproc/avow";
import type { ReactNode } from "react";

/**
 * The four render states, all mutually exclusive:
 * - `checking`  — the async verify has not resolved yet (fail-closed default).
 * - `verified`  — the injected verify resolved AND the signer is the pinned key.
 * - `invalid`   — verify rejected: tampered payload or bad signature bytes.
 * - `wrong-key` — the embedded public key is not the caller-pinned signer.
 */
export type ReceiptStatus = "checking" | "verified" | "invalid" | "wrong-key";

/** The verify contract: resolve if the receipt is valid, reject otherwise. */
export type VerifyFn<S extends JsonValue> = (
  receipt: SignedReceipt<S>,
  expectedPublicKey: string,
) => Promise<void>;

/** Props common to every receipt view. */
export interface ReceiptVerificationProps<S extends JsonValue> {
  /** The signed receipt to render and verify. */
  receipt: SignedReceipt<S>;
  /** The only signer the caller trusts; a mismatch renders `wrong-key`. */
  expectedPublicKey: string;
  /** Injected verifier; defaults to avow's own `verifySignature`. */
  verify?: VerifyFn<S>;
}

/** Props for the full panel: the verification props plus a payload render-prop. */
export interface ReceiptPanelProps<S extends JsonValue>
  extends ReceiptVerificationProps<S> {
  /** Render the subject-specific body. Omit to hide the payload section. */
  renderPayload?: (payload: S) => ReactNode;
}
