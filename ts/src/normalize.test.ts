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
});
