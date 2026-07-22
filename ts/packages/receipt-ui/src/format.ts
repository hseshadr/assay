const HEAD = 6;
const TAIL = 6;

/**
 * Abbreviate a long hex string to `head…tail` for display, leaving any string
 * already short enough to fit fully intact. Purely cosmetic — never used for
 * comparison, so truncation can never mask a mismatched key or signature.
 */
export function shortenHex(hex: string, head = HEAD, tail = TAIL): string {
  if (hex.length <= head + tail + 1) {
    return hex;
  }
  return `${hex.slice(0, head)}…${hex.slice(-tail)}`;
}
