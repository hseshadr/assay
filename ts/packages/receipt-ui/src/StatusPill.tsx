import type { ReactElement } from "react";
import type { ReceiptLabels, ReceiptStatus } from "./types.js";

interface Label {
  icon: string;
  text: string;
}

// Every state carries a distinct icon AND a distinct word label, so the verdict
// survives without color (WCAG 1.4.1). The `invalid` and `wrong-key` texts both
// lead with "Not verified" — the fail-closed states must read as such at a
// glance — while staying clearly distinguishable. These are the defaults;
// apps override any of them (i18n) via the `labels` prop.
const DEFAULT_LABELS: Record<ReceiptStatus, Label> = {
  checking: { icon: "…", text: "Verifying…" },
  verified: { icon: "✓", text: "Verified" },
  invalid: { icon: "✕", text: "Not verified — tampered or invalid signature" },
  "wrong-key": { icon: "⚠", text: "Not verified — untrusted signer" },
};

/** The presentational status chip: a live `role="status"` region, icon + text. */
export function StatusPill({
  status,
  labels,
}: {
  status: ReceiptStatus;
  /** Injected strings (i18n); omitted fields keep the English defaults. */
  labels?: ReceiptLabels | undefined;
}): ReactElement {
  const override = labels?.status?.[status];
  const icon = override?.icon ?? DEFAULT_LABELS[status].icon;
  const text = override?.text ?? DEFAULT_LABELS[status].text;
  return (
    <span className="receipt-status" data-status={status} role="status">
      <span aria-hidden="true" className="receipt-status__icon">
        {icon}
      </span>
      <span className="receipt-status__text">{text}</span>
    </span>
  );
}
