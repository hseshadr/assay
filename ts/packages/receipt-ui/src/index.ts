/**
 * `@edgeproc/receipt-ui` — render and verify an Avow `SignedReceipt` in React.
 *
 * A composable badge and panel that verify a receipt on mount and render one of
 * four clearly-distinct states — verifying, verified, invalid (tampered), or
 * untrusted signer. Fail-closed: only a resolved verify under the pinned key
 * reads as verified. Verification is injectable per app and defaults to avow's
 * own `verifySignature`, so `@edgeproc/avow` stays framework-agnostic.
 */

export { shortenHex } from "./format.js";
export { ReceiptBadge } from "./ReceiptBadge.js";
export { ReceiptPanel } from "./ReceiptPanel.js";
export { StatusPill } from "./StatusPill.js";
export type {
  PanelLabels,
  ReceiptLabels,
  ReceiptPanelProps,
  ReceiptStatus,
  ReceiptVerificationProps,
  StatusLabelOverride,
  VerifyFn,
} from "./types.js";
export { useReceiptVerification } from "./useReceiptVerification.js";
