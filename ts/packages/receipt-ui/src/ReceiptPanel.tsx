import { type JsonValue, verifySignature } from "@edgeproc/avow";
import type { ReactElement } from "react";
import { shortenHex } from "./format.js";
import { StatusPill } from "./StatusPill.js";
import type { ReceiptPanelProps } from "./types.js";
import { useReceiptVerification } from "./useReceiptVerification.js";

// Avow envelopes are Ed25519-only, so the algorithm is a constant rather than a
// field on the receipt.
const ALGORITHM = "Ed25519";

/**
 * Full receipt view: the verification verdict, the envelope metadata (algorithm,
 * shortened signer key, payload hash and signature), and — via `renderPayload` —
 * the subject-specific body. Same fail-closed verification as `ReceiptBadge`.
 */
export function ReceiptPanel<S extends JsonValue>(
  props: ReceiptPanelProps<S>,
): ReactElement {
  const { receipt, expectedPublicKey, renderPayload, labels } = props;
  const verify = props.verify ?? verifySignature;
  const status = useReceiptVerification(receipt, expectedPublicKey, verify);
  const meta = labels?.panel;
  return (
    <section
      aria-label={meta?.receipt ?? "Signed receipt"}
      className="receipt-panel"
    >
      <StatusPill status={status} labels={labels} />
      <dl className="receipt-panel__meta">
        <div className="receipt-panel__row">
          <dt>{meta?.algorithm ?? "Algorithm"}</dt>
          <dd>{ALGORITHM}</dd>
        </div>
        <div className="receipt-panel__row">
          <dt>{meta?.signerKey ?? "Signer key"}</dt>
          <dd>
            <code>{shortenHex(receipt.public_key)}</code>
          </dd>
        </div>
        <div className="receipt-panel__row">
          <dt>{meta?.payloadHash ?? "Payload hash"}</dt>
          <dd>
            <code>{shortenHex(receipt.payload_hash)}</code>
          </dd>
        </div>
        <div className="receipt-panel__row">
          <dt>{meta?.signature ?? "Signature"}</dt>
          <dd>
            <code>{shortenHex(receipt.signature)}</code>
          </dd>
        </div>
      </dl>
      {renderPayload ? (
        <div className="receipt-panel__payload">
          {renderPayload(receipt.payload)}
        </div>
      ) : null}
    </section>
  );
}
