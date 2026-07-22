import { type JsonValue, verifySignature } from "@edgeproc/avow";
import type { ReactElement } from "react";
import { StatusPill } from "./StatusPill.js";
import type { ReceiptVerificationProps } from "./types.js";
import { useReceiptVerification } from "./useReceiptVerification.js";

/**
 * Compact one-line verdict for a signed receipt. Verifies on mount (via the
 * injected `verify`, defaulting to avow's `verifySignature`) and renders one of
 * four clearly-distinct states. Fail-closed: anything but a resolved verify
 * under the pinned key renders as not-verified.
 */
export function ReceiptBadge<S extends JsonValue>(
  props: ReceiptVerificationProps<S>,
): ReactElement {
  const verify = props.verify ?? verifySignature;
  const status = useReceiptVerification(
    props.receipt,
    props.expectedPublicKey,
    verify,
  );
  return <StatusPill status={status} />;
}
