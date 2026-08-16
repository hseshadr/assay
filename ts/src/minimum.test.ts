import { describe, expect, it } from "vitest";

import { minimum, parseRequest } from "./index.js";

describe("minimum", () => {
  it("selects the first declared minimum and propagates candidate bounds", () => {
    const request = parseRequest({
      method: "minimum",
      method_version: "demo.v1",
      components: [
        {
          id: "z-first",
          label: "First",
          value: 5,
          scale: {
            minimum: 0,
            maximum: 10,
            direction: "higher_is_better",
          },
          interval: { low: 4, high: 6 },
        },
        {
          id: "a-second",
          label: "Second",
          value: 5,
          scale: {
            minimum: 0,
            maximum: 10,
            direction: "higher_is_better",
          },
          interval: { low: 3, high: 7 },
        },
      ],
      clamp: "reject",
    });
    if (request.method !== "minimum") throw new Error("wrong request");

    const result = minimum(request);

    expect(result).toMatchObject({
      method: { id: "minimum", version: "demo.v1" },
      score: 0.5,
      interval: { low: 0.3, high: 0.6 },
      clamp: "reject",
      intercept: null,
      weight_total: null,
      selected_component_id: "z-first",
    });
    expect(result.components.map((row) => row.id)).toEqual([
      "z-first",
      "a-second",
    ]);
    expect(result.components.map((row) => row.contribution_interval)).toEqual([
      { low: 0.4, high: 0.6 },
      { low: 0.3, high: 0.7 },
    ]);
  });
});
