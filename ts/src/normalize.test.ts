import { readFile } from "node:fs/promises";

import { describe, expect, it } from "vitest";

import { normalize } from "./index.js";

interface NormalizeVector {
  readonly value: number;
  readonly minimum: number;
  readonly maximum: number;
  readonly direction: "higher_is_better" | "lower_is_better";
  readonly clamp: "reject" | "clamp";
  readonly normalized: number;
}

async function vectors(): Promise<ReadonlyArray<NormalizeVector>> {
  const path = new URL(
    "../../testdata/vectors/normalize.json",
    import.meta.url,
  );
  const text = await readFile(path, "utf8");
  return JSON.parse(text) as ReadonlyArray<NormalizeVector>;
}

describe("normalize", () => {
  it("executes every shared Python normalization vector", async () => {
    const cases = await vectors();
    expect(cases).toHaveLength(9);

    const executed = cases.map((vector, index) => {
      const actual = normalize(
        vector.value,
        {
          minimum: vector.minimum,
          maximum: vector.maximum,
          direction: vector.direction,
        },
        vector.clamp,
      );
      expect(actual).toBe(vector.normalized);
      return `normalize-${index}`;
    });

    expect(new Set(executed).size).toBe(cases.length);
  });

  it("rejects non-finite intermediate binary64 arithmetic", () => {
    expect(() =>
      normalize(
        0,
        {
          minimum: -1e308,
          maximum: 1e308,
          direction: "higher_is_better",
        },
        "clamp",
      ),
    ).toThrow("assay.invalid_number");
    expect(() =>
      normalize(
        1e308,
        {
          minimum: 0,
          maximum: Number.MIN_VALUE,
          direction: "higher_is_better",
        },
        "clamp",
      ),
    ).toThrow("assay.invalid_number");
  });

  it("rejects an out-of-range value under the reject policy", () => {
    expect(() =>
      normalize(
        2,
        { minimum: 0, maximum: 1, direction: "higher_is_better" },
        "reject",
      ),
    ).toThrow("assay.out_of_range");
  });
});
