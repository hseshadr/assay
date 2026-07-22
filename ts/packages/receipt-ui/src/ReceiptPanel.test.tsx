import {
  generateSeedHex,
  type JsonValue,
  publicKeyHex,
  type SignedReceipt,
  signPayload,
} from "@edgeproc/avow";
import { render, screen, waitFor } from "@testing-library/react";
import { beforeAll, describe, expect, it } from "vitest";
import { shortenHex } from "./format.js";
import { ReceiptPanel } from "./ReceiptPanel.js";

const payload = { kind: "score", score: 0.87 } satisfies JsonValue;
let signerKey: string;
let valid: SignedReceipt<typeof payload>;

beforeAll(async () => {
  const seed = generateSeedHex();
  signerKey = await publicKeyHex(seed);
  valid = await signPayload(payload, seed);
});

const panel = () => screen.getByRole("region", { name: /signed receipt/i });

describe("ReceiptPanel envelope metadata", () => {
  it("shows the algorithm and the shortened key, hash and signature", () => {
    render(<ReceiptPanel receipt={valid} expectedPublicKey={signerKey} />);
    const text = panel().textContent ?? "";
    expect(text).toContain("Ed25519");
    expect(text).toContain(shortenHex(valid.public_key));
    expect(text).toContain(shortenHex(valid.payload_hash));
    expect(text).toContain(shortenHex(valid.signature));
  });

  it("renders the subject body via the renderPayload render-prop", () => {
    render(
      <ReceiptPanel
        receipt={valid}
        expectedPublicKey={signerKey}
        renderPayload={(p) => <span>score is {p.score}</span>}
      />,
    );
    expect(panel().textContent).toContain("score is 0.87");
  });

  it("omits the payload section when no renderPayload is given", () => {
    render(<ReceiptPanel receipt={valid} expectedPublicKey={signerKey} />);
    expect(panel().querySelector(".receipt-panel__payload")).toBeNull();
  });
});

describe("ReceiptPanel verification verdict", () => {
  it("embeds the status pill and reaches VERIFIED with a resolving verify", async () => {
    render(
      <ReceiptPanel
        receipt={valid}
        expectedPublicKey={signerKey}
        verify={() => Promise.resolve()}
      />,
    );
    await waitFor(() =>
      expect(screen.getByRole("status").getAttribute("data-status")).toBe(
        "verified",
      ),
    );
  });
});
