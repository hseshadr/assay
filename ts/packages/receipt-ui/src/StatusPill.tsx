import type { ReactElement } from "react";
import type { ReceiptStatus } from "./types.js";

interface Label {
  icon: string;
  text: string;
}

// Every state carries a distinct icon AND a distinct word label, so the verdict
// survives without color (WCAG 1.4.1). The `invalid` and `wrong-key` texts both
// lead with "Not verified" — the fail-closed states must read as such at a
// glance — while staying clearly distinguishable.
const LABELS: Record<ReceiptStatus, Label> = {
  checking: { icon: "…", text: "Verifying…" },
  verified: { icon: "✓", text: "Verified" },
  invalid: { icon: "✕", text: "Not verified — tampered or invalid signature" },
  "wrong-key": { icon: "⚠", text: "Not verified — untrusted signer" },
};

/** The presentational status chip: a live `role="status"` region, icon + text. */
export function StatusPill({
  status,
}: {
  status: ReceiptStatus;
}): ReactElement {
  const { icon, text } = LABELS[status];
  return (
    <span className="receipt-status" data-status={status} role="status">
      <span aria-hidden="true" className="receipt-status__icon">
        {icon}
      </span>
      <span className="receipt-status__text">{text}</span>
    </span>
  );
}
