import {
  generateSeedHex,
  type JsonValue,
  publicKeyHex,
  type SignedReceipt,
  signPayload,
} from "@edgeproc/avow";
import { render, screen, waitFor } from "@testing-library/react";
import { beforeAll, describe, expect, it } from "vitest";
import { ReceiptBadge } from "./ReceiptBadge.js";

// Real avow fixtures — the property under test is "does the badge reflect what
// avow's own verifier decides", so nothing here is mocked. Built once.
const payload = { kind: "score", score: 0.87 } satisfies JsonValue;
let signerKey: string;
let untrustedKey: string;
let valid: SignedReceipt<typeof payload>;
let tampered: SignedReceipt<typeof payload>;

beforeAll(async () => {
  const seed = generateSeedHex();
  signerKey = await publicKeyHex(seed);
  untrustedKey = await publicKeyHex(generateSeedHex());
  valid = await signPayload(payload, seed);
  // Mutate the payload AFTER signing: the stored hash/signature now describe a
  // different subject, so avow's verifier recomputes a mismatching hash.
  tampered = { ...valid, payload: { ...payload, score: 0.99 } };
});

const status = () => screen.getByRole("status");

describe("ReceiptBadge verification verdict", () => {
  it("shows VERIFIED for a valid receipt under the pinned key", async () => {
    render(<ReceiptBadge receipt={valid} expectedPublicKey={signerKey} />);
    await waitFor(() =>
      expect(status().getAttribute("data-status")).toBe("verified"),
    );
    expect(status().textContent).toMatch(/verified/i);
  });

  it("shows NOT-verified (invalid) for a tampered receipt", async () => {
    render(<ReceiptBadge receipt={tampered} expectedPublicKey={signerKey} />);
    await waitFor(() =>
      expect(status().getAttribute("data-status")).toBe("invalid"),
    );
    expect(status().getAttribute("data-status")).not.toBe("verified");
    expect(status().textContent).toMatch(/not verified/i);
  });

  it("shows WRONG-KEY for a receipt signed by an untrusted signer", async () => {
    render(<ReceiptBadge receipt={valid} expectedPublicKey={untrustedKey} />);
    await waitFor(() =>
      expect(status().getAttribute("data-status")).toBe("wrong-key"),
    );
    expect(status().textContent).toMatch(/untrusted signer/i);
  });

  it("renders as CHECKING (not verified) before the async verify resolves", async () => {
    render(<ReceiptBadge receipt={valid} expectedPublicKey={signerKey} />);
    expect(status().getAttribute("data-status")).toBe("checking");
    await waitFor(() =>
      expect(status().getAttribute("data-status")).toBe("verified"),
    );
  });
});

describe("ReceiptBadge fails closed and trusts the injected verify", () => {
  it("shows NOT-verified when the injected verify rejects", async () => {
    const rejecting = () => Promise.reject(new Error("verifier unavailable"));
    render(
      <ReceiptBadge
        receipt={valid}
        expectedPublicKey={signerKey}
        verify={rejecting}
      />,
    );
    await waitFor(() =>
      expect(status().getAttribute("data-status")).toBe("invalid"),
    );
  });

  it("only shows VERIFIED on a tampered receipt when a stub verify resolves", async () => {
    // The badge trusts the injected verifier: an always-resolve stub is the
    // ONLY way a tampered receipt reads green. With the real verifier (the
    // tampered test above) the same receipt reads `invalid`.
    const alwaysOk = () => Promise.resolve();
    render(
      <ReceiptBadge
        receipt={tampered}
        expectedPublicKey={signerKey}
        verify={alwaysOk}
      />,
    );
    await waitFor(() =>
      expect(status().getAttribute("data-status")).toBe("verified"),
    );
  });

  it("does not update state after unmount while a verify is in flight", async () => {
    let settle: () => void = () => undefined;
    const gated = new Promise<void>((resolve) => {
      settle = resolve;
    });
    const { unmount } = render(
      <ReceiptBadge
        receipt={valid}
        expectedPublicKey={signerKey}
        verify={() => gated}
      />,
    );
    expect(status().getAttribute("data-status")).toBe("checking");
    unmount();
    settle();
    await gated;
    // No assertion beyond a clean run: a post-unmount setState would raise an
    // act(...) warning and fail the pristine-output gate.
  });
});

describe("ReceiptBadge accessibility", () => {
  it("exposes a status role and conveys state by text + icon, not color", async () => {
    render(<ReceiptBadge receipt={valid} expectedPublicKey={signerKey} />);
    await waitFor(() =>
      expect(status().getAttribute("data-status")).toBe("verified"),
    );
    const icon = status().querySelector("[aria-hidden='true']");
    expect(icon).not.toBeNull();
    expect(status().textContent?.trim().length ?? 0).toBeGreaterThan(0);
  });
});
