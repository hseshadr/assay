import { describe, expect, it } from "vitest";

import { type AdditiveRequest, additive, parseRequest } from "./index.js";

describe("additive", () => {
  it("adds and subtracts left to right before applying the final policy", () => {
    const request = parseRequest({
      method: "additive",
      method_version: "demo.v1",
      intercept: 0.2,
      terms: [
        {
          id: "base",
          label: "Base",
          value: 0.5,
          coefficient: 1,
          operation: "add",
          interval: { low: 0.4, high: 0.6 },
        },
        {
          id: "penalty",
          label: "Penalty",
          value: 0.1,
          coefficient: 2,
          operation: "subtract",
          interval: { low: 0.05, high: 0.15 },
        },
      ],
      clamp: "reject",
    });
    if (request.method !== "additive") throw new Error("wrong request");

    const result = additive(request);

    expect(result).toMatchObject({
      method: { id: "additive", version: "demo.v1" },
      score: 0.49999999999999994,
      interval: { low: 0.3000000000000001, high: 0.7000000000000001 },
      clamp: "reject",
      intercept: 0.2,
      weight_total: null,
      selected_component_id: null,
    });
    expect(result.components).toEqual([
      {
        id: "base",
        raw: 0.5,
        normalized: null,
        declared_weight: null,
        operation: "add",
        coefficient: 1,
        contribution: 0.5,
        contribution_interval: { low: 0.4, high: 0.6 },
      },
      {
        id: "penalty",
        raw: 0.1,
        normalized: null,
        declared_weight: null,
        operation: "subtract",
        coefficient: 2,
        contribution: 0.2,
        contribution_interval: { low: 0.1, high: 0.3 },
      },
    ]);
  });

  it("rejects non-finite term arithmetic and an out-of-range final score", () => {
    const overflow = parseRequest({
      method: "additive",
      method_version: "overflow.v1",
      terms: [
        {
          id: "term",
          label: "Term",
          value: 1e308,
          coefficient: 2,
          operation: "add",
        },
      ],
      clamp: null,
    });
    const rejected = parseRequest({
      method: "additive",
      method_version: "reject.v1",
      terms: [
        {
          id: "term",
          label: "Term",
          value: 2,
          coefficient: 1,
          operation: "add",
        },
      ],
      clamp: "reject",
    });
    if (overflow.method !== "additive" || rejected.method !== "additive") {
      throw new Error("wrong request");
    }

    expect(() => additive(overflow)).toThrow("assay.invalid_number");
    expect(() => additive(rejected)).toThrow("assay.out_of_range");
  });

  it("collapses the final interval only after clamping its endpoints", () => {
    const request = parseRequest({
      method: "additive",
      method_version: "clamp.v1",
      terms: [
        {
          id: "term",
          label: "Term",
          value: 2.5,
          coefficient: 1,
          operation: "add",
          interval: { low: 2, high: 3 },
        },
      ],
      clamp: "clamp",
    });
    if (request.method !== "additive") throw new Error("wrong request");

    const result = additive(request);

    expect(result.score).toBe(1);
    expect(result.interval).toBeNull();
    expect(result.components[0]?.contribution_interval).toEqual({
      low: 2,
      high: 3,
    });
  });

  it("rejects a request for a different method", () => {
    const request = parseRequest({
      method: "minimum",
      method_version: "wrong.v1",
      components: [
        {
          id: "quality",
          label: "Quality",
          value: 1,
          scale: { minimum: 0, maximum: 1, direction: "higher_is_better" },
        },
      ],
      clamp: "reject",
    });

    expect(() => additive(request as unknown as AdditiveRequest)).toThrow(
      "assay.invalid_method",
    );
  });
});
