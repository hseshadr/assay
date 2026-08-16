import { describe, expect, it } from "vitest";

import { type MinimumRequest, minimum, parseRequest } from "./index.js";

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

  it("supports mixed deterministic and uncertain candidates", () => {
    const request = parseRequest({
      method: "minimum",
      method_version: "mixed.v1",
      components: [
        {
          id: "latency",
          label: "Latency",
          value: 8,
          scale: {
            minimum: 0,
            maximum: 10,
            direction: "lower_is_better",
          },
        },
        {
          id: "quality",
          label: "Quality",
          value: 0.7,
          scale: { minimum: 0, maximum: 1, direction: "higher_is_better" },
          interval: { low: 0.6, high: 0.8 },
        },
      ],
      clamp: "reject",
    });
    if (request.method !== "minimum") throw new Error("wrong request");

    const result = minimum(request);

    expect(result.score).toBe(0.2);
    expect(result.interval).toBeNull();
    expect(result.components[0]?.contribution_interval).toBeNull();
  });

  it("collapses deterministic and fully clamped intervals", () => {
    const deterministic = parseRequest({
      method: "minimum",
      method_version: "plain.v1",
      components: [
        {
          id: "quality",
          label: "Quality",
          value: 0.5,
          scale: { minimum: 0, maximum: 1, direction: "higher_is_better" },
        },
      ],
      clamp: "reject",
    });
    const clamped = parseRequest({
      method: "minimum",
      method_version: "clamp.v1",
      components: [
        {
          id: "quality",
          label: "Quality",
          value: 2.5,
          scale: { minimum: 0, maximum: 1, direction: "higher_is_better" },
          interval: { low: 2, high: 3 },
        },
      ],
      clamp: "clamp",
    });
    if (deterministic.method !== "minimum" || clamped.method !== "minimum") {
      throw new Error("wrong request");
    }

    expect(minimum(deterministic).interval).toBeNull();
    expect(minimum(clamped).interval).toBeNull();
  });

  it("rejects a request for a different method", () => {
    const request = parseRequest({
      method: "additive",
      method_version: "wrong.v1",
      terms: [
        {
          id: "term",
          label: "Term",
          value: 1,
          coefficient: 1,
          operation: "add",
        },
      ],
      clamp: null,
    });

    expect(() => minimum(request as unknown as MinimumRequest)).toThrow(
      "assay.invalid_method",
    );
  });
});
