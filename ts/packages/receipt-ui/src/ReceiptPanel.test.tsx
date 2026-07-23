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

describe("ReceiptPanel injectable labels", () => {
  const dtTexts = (region: HTMLElement) =>
    Array.from(region.querySelectorAll("dt")).map((dt) => dt.textContent);

  it("keeps the exact 0.1.0 meta labels and aria-label when labels is omitted", () => {
    render(<ReceiptPanel receipt={valid} expectedPublicKey={signerKey} />);
    const region = screen.getByRole("region", { name: "Signed receipt" });
    expect(dtTexts(region)).toEqual([
      "Algorithm",
      "Signer key",
      "Payload hash",
      "Signature",
    ]);
  });

  it("renders injected meta labels and section aria-label", () => {
    render(
      <ReceiptPanel
        receipt={valid}
        expectedPublicKey={signerKey}
        labels={{
          panel: {
            receipt: "Signierter Beleg",
            algorithm: "Algorithmus",
            signerKey: "Schlüssel des Unterzeichners",
            payloadHash: "Hash der Nutzdaten",
            signature: "Signaturwert",
          },
        }}
      />,
    );
    const region = screen.getByRole("region", { name: "Signierter Beleg" });
    expect(dtTexts(region)).toEqual([
      "Algorithmus",
      "Schlüssel des Unterzeichners",
      "Hash der Nutzdaten",
      "Signaturwert",
    ]);
  });

  it("merges partial panel labels with the English defaults", () => {
    render(
      <ReceiptPanel
        receipt={valid}
        expectedPublicKey={signerKey}
        labels={{ panel: { algorithm: "Algorithmus" } }}
      />,
    );
    const region = screen.getByRole("region", { name: "Signed receipt" });
    expect(dtTexts(region)).toEqual([
      "Algorithmus",
      "Signer key",
      "Payload hash",
      "Signature",
    ]);
  });

  it("forwards status labels to the embedded pill", async () => {
    render(
      <ReceiptPanel
        receipt={valid}
        expectedPublicKey={signerKey}
        verify={() => Promise.resolve()}
        labels={{ status: { verified: { text: "Vérifié" } } }}
      />,
    );
    await waitFor(() =>
      expect(screen.getByRole("status").textContent).toContain("Vérifié"),
    );
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
