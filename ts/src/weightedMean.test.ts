import { describe, expect, it } from "vitest";

import {
  parseRequest,
  type WeightedMeanRequest,
  weightedMean,
} from "./index.js";

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

  it("returns a deterministic lower-is-better result without an interval", () => {
    const request = parseRequest({
      method: "weighted_mean",
      method_version: "deterministic.v1",
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
          weight: 1,
        },
      ],
      clamp: "reject",
    });
    if (request.method !== "weighted_mean") throw new Error("wrong request");

    const result = weightedMean(request);

    expect(result.score).toBe(0.2);
    expect(result.interval).toBeNull();
    expect(result.components[0]?.contribution_interval).toBeNull();
  });

  it("collapses a fully clamped component interval", () => {
    const request = parseRequest({
      method: "weighted_mean",
      method_version: "clamped.v1",
      components: [
        {
          id: "quality",
          label: "Quality",
          value: 2,
          scale: {
            minimum: 0,
            maximum: 1,
            direction: "higher_is_better",
          },
          interval: { low: 2, high: 3 },
          weight: 1,
        },
      ],
      clamp: "clamp",
    });
    if (request.method !== "weighted_mean") throw new Error("wrong request");

    const result = weightedMean(request);

    expect(result.score).toBe(1);
    expect(result.interval).toBeNull();
    expect(result.components[0]?.contribution_interval).toBeNull();
  });

  it("matches Python when distinct row bounds collapse after ordered summation", () => {
    const request = parseRequest({
      method: "weighted_mean",
      method_version: "collapse.v1",
      components: [
        {
          id: "first",
          label: "First",
          value: 1,
          scale: { minimum: 0, maximum: 1, direction: "higher_is_better" },
          weight: 1,
        },
        {
          id: "second",
          label: "Second",
          value: 1.0000000000000001e-16,
          scale: { minimum: 0, maximum: 1, direction: "higher_is_better" },
          interval: { low: 1e-16, high: 1.0000000000000002e-16 },
          weight: 1,
        },
      ],
      clamp: "reject",
    });
    if (request.method !== "weighted_mean") throw new Error("wrong request");

    const result = weightedMean(request);

    expect(result.score).toBe(0.5);
    expect(result.interval).toBeNull();
    expect(result.inputs_hash).toBe(
      "sha256:db971d392461287de1798999a33f4afbfda3f9ec433f76104347aec7a11ca1a7",
    );
  });

  it("rejects non-finite weighted arithmetic", () => {
    const request = parseRequest({
      method: "weighted_mean",
      method_version: "overflow.v1",
      components: [
        {
          id: "first",
          label: "First",
          value: 1,
          scale: { minimum: 0, maximum: 1, direction: "higher_is_better" },
          weight: 1e308,
        },
        {
          id: "second",
          label: "Second",
          value: 1,
          scale: { minimum: 0, maximum: 1, direction: "higher_is_better" },
          weight: 1e308,
        },
      ],
      clamp: "reject",
    });
    if (request.method !== "weighted_mean") throw new Error("wrong request");

    expect(() => weightedMean(request)).toThrow("assay.invalid_number");
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

    expect(() =>
      weightedMean(request as unknown as WeightedMeanRequest),
    ).toThrow("assay.invalid_method");
  });
});
