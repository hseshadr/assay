import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { StatusPill } from "./StatusPill.js";
import type { ReceiptStatus } from "./types.js";

const status = () => screen.getByRole("status");
const iconOf = () => status().querySelector(".receipt-status__icon");
const textOf = () => status().querySelector(".receipt-status__text");

// The exact 0.1.0 strings — the backward-compatibility contract. A consumer
// that never passes `labels` must render byte-identically to 0.1.0.
const DEFAULTS: Record<ReceiptStatus, { icon: string; text: string }> = {
  checking: { icon: "…", text: "Verifying…" },
  verified: { icon: "✓", text: "Verified" },
  invalid: { icon: "✕", text: "Not verified — tampered or invalid signature" },
  "wrong-key": { icon: "⚠", text: "Not verified — untrusted signer" },
};
const STATUSES = Object.keys(DEFAULTS) as ReceiptStatus[];

describe("StatusPill default labels (the 0.1.0 contract)", () => {
  for (const state of STATUSES) {
    it(`renders the exact built-in icon and text for ${state} when labels is omitted`, () => {
      render(<StatusPill status={state} />);
      expect(iconOf()?.textContent).toBe(DEFAULTS[state].icon);
      expect(textOf()?.textContent).toBe(DEFAULTS[state].text);
    });
  }
});

describe("StatusPill injectable labels", () => {
  for (const state of STATUSES) {
    it(`renders injected text for ${state}`, () => {
      render(
        <StatusPill
          status={state}
          labels={{ status: { [state]: { text: `loc-${state}` } } }}
        />,
      );
      expect(textOf()?.textContent).toBe(`loc-${state}`);
    });
  }

  it("renders an injected icon", () => {
    render(
      <StatusPill
        status="verified"
        labels={{ status: { verified: { icon: "☑" } } }}
      />,
    );
    expect(iconOf()?.textContent).toBe("☑");
  });

  it("merges a text-only override with the default icon", () => {
    render(
      <StatusPill
        status="verified"
        labels={{ status: { verified: { text: "Vérifié" } } }}
      />,
    );
    expect(textOf()?.textContent).toBe("Vérifié");
    expect(iconOf()?.textContent).toBe(DEFAULTS.verified.icon);
  });

  it("ignores a blank text/icon override and keeps the default verdict (never empty)", () => {
    render(
      <StatusPill
        status="verified"
        labels={{ status: { verified: { text: "  ", icon: "" } } }}
      />,
    );
    expect(textOf()?.textContent).toBe(DEFAULTS.verified.text);
    expect(iconOf()?.textContent).toBe(DEFAULTS.verified.icon);
  });

  it("falls back to the default for states the override does not name", () => {
    render(
      <StatusPill
        status="invalid"
        labels={{ status: { verified: { text: "Vérifié" } } }}
      />,
    );
    expect(textOf()?.textContent).toBe(DEFAULTS.invalid.text);
    expect(iconOf()?.textContent).toBe(DEFAULTS.invalid.icon);
  });
});
