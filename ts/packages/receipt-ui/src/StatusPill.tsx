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

// `??` only falls back on null/undefined, so a blank ("" or whitespace) override would
// blank out the verdict — the one thing a fail-closed status chip must never do. Treat a
// blank override as "unset" and keep the built-in default.
const nonBlank = (value: string | undefined): string | undefined =>
  value !== undefined && value.trim() !== "" ? value : undefined;

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
  const icon = nonBlank(override?.icon) ?? DEFAULT_LABELS[status].icon;
  const text = nonBlank(override?.text) ?? DEFAULT_LABELS[status].text;
  return (
    <span className="receipt-status" data-status={status} role="status">
      <span aria-hidden="true" className="receipt-status__icon">
        {icon}
      </span>
      <span className="receipt-status__text">{text}</span>
    </span>
  );
}
