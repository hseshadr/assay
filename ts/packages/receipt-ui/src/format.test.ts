import { describe, expect, it } from "vitest";
import { shortenHex } from "./format.js";

describe("shortenHex", () => {
  it("abbreviates a long hex string to head…tail", () => {
    const hex = "0123456789abcdef0123456789abcdef";
    expect(shortenHex(hex)).toBe("012345…abcdef");
  });

  it("leaves a string short enough to fit fully intact", () => {
    expect(shortenHex("0123456789")).toBe("0123456789");
  });
});
