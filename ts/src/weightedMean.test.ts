import { describe, expect, it } from "vitest";

import { parseRequest, weightedMean } from "./index.js";

describe("weightedMean", () => {
  it("normalizes, weights, and propagates intervals in declared order", () => {
    const request = parseRequest({
      method: "weighted_mean",
      method_version: "demo.v1",
      components: [
        {
          id: "quality",
          label: "Quality",
          value: 5,
          scale: {
            minimum: 0,
            maximum: 10,
            direction: "higher_is_better",
          },
          interval: { low: 4, high: 6 },
          weight: 1,
        },
        {
          id: "speed",
          label: "Speed",
          value: 8,
          scale: {
            minimum: 0,
            maximum: 10,
            direction: "higher_is_better",
          },
          interval: null,
          weight: 3,
        },
      ],
      clamp: "reject",
    });
    if (request.method !== "weighted_mean") throw new Error("wrong request");

    const result = weightedMean(request);

    expect(result).toMatchObject({
      schema: "assay.result/v1",
      method: { id: "weighted_mean", version: "demo.v1" },
      score: 0.7250000000000001,
      interval: { low: 0.7000000000000001, high: 0.7500000000000001 },
      clamp: "reject",
      intercept: null,
      weight_total: 4,
      selected_component_id: null,
    });
    expect(result.components).toEqual([
      {
        id: "quality",
        raw: 5,
        normalized: 0.5,
        declared_weight: 1,
        operation: "add",
        coefficient: 0.25,
        contribution: 0.125,
        contribution_interval: { low: 0.1, high: 0.15 },
      },
      {
        id: "speed",
        raw: 8,
        normalized: 0.8,
        declared_weight: 3,
        operation: "add",
        coefficient: 0.75,
        contribution: 0.6000000000000001,
        contribution_interval: null,
      },
    ]);
    expect(result.inputs_hash).toMatch(/^sha256:[0-9a-f]{64}$/u);
  });
});
