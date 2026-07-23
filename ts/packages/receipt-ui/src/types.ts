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

/** Override one verdict's rendering: the visible text and/or the icon glyph. */
export interface StatusLabelOverride {
  /** Replaces the visible verdict text (e.g. a translated "Verified"). */
  text?: string;
  /** Replaces the aria-hidden icon glyph. */
  icon?: string;
}

/** Overrides for the panel's envelope-metadata strings. */
export interface PanelLabels {
  /** The panel section's `aria-label` (default "Signed receipt"). */
  receipt?: string;
  /** Row label for the signature algorithm (default "Algorithm"). */
  algorithm?: string;
  /** Row label for the signer's public key (default "Signer key"). */
  signerKey?: string;
  /** Row label for the payload hash (default "Payload hash"). */
  payloadHash?: string;
  /** Row label for the signature bytes (default "Signature"). */
  signature?: string;
}

/**
 * Every string this package renders, injectable so apps can localize. Deep
 * partial: omit anything to keep the built-in English default — a consumer
 * that passes nothing renders exactly the 0.1.0 strings.
 */
export interface ReceiptLabels {
  /** Per-verdict text/icon overrides, keyed by `ReceiptStatus`. */
  status?: Partial<Record<ReceiptStatus, StatusLabelOverride>>;
  /** The panel's envelope-metadata labels. */
  panel?: PanelLabels;
}

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
  /** Injected strings (i18n); omitted fields keep the English defaults. */
  labels?: ReceiptLabels;
}

/** Props for the full panel: the verification props plus a payload render-prop. */
export interface ReceiptPanelProps<S extends JsonValue>
  extends ReceiptVerificationProps<S> {
  /** Render the subject-specific body. Omit to hide the payload section. */
  renderPayload?: (payload: S) => ReactNode;
}
