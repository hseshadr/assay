import { describe, expect, it } from "vitest";

import {
  parseRequest,
  parseRequestJson,
  parseScoreResult,
  parseScoreResultJson,
} from "./index.js";

const HASH = `sha256:${"0".repeat(64)}`;

function weightedInput(): Record<string, unknown> {
  return {
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
        interval: null,
        weight: 2,
      },
    ],
    clamp: "reject",
  };
}

function weightedResult(): Record<string, unknown> {
  return {
    schema: "assay.result/v1",
    method: { id: "weighted_mean", version: "demo.v1" },
    score: 0.5,
    interval: null,
    clamp: "reject",
    intercept: null,
    weight_total: 2,
    components: [
      {
        id: "quality",
        raw: 5,
        normalized: 0.5,
        declared_weight: 2,
        operation: "add",
        coefficient: 1,
        contribution: 0.5,
        contribution_interval: null,
      },
    ],
    inputs_hash: HASH,
    selected_component_id: null,
  };
}

function errorFrom(action: () => unknown): Error & { readonly code?: unknown } {
  try {
    action();
  } catch (error: unknown) {
    if (error instanceof Error) {
      return error;
    }
  }
  throw new Error("expected a contract error");
}

function expectCode(action: () => unknown, code: string): void {
  const error = errorFrom(action);
  expect(error.message).toBe(code);
  expect(error.code).toBe(code);
}

describe("parseRequest", () => {
  it("parses and freezes a weighted-mean request", () => {
    const input = weightedInput();
    const request = parseRequest(input);

    expect(request).toEqual(input);
    if (request.method !== "weighted_mean") {
      throw new Error("expected weighted mean");
    }
    expect(Object.isFrozen(request)).toBe(true);
    expect(Object.isFrozen(request.components)).toBe(true);
    expect(request).not.toBe(input);
  });

  it("fills documented null and numeric defaults", () => {
    const request = parseRequest({
      method: "additive",
      method_version: "demo.v1",
      terms: [
        {
          id: "base",
          label: "Base",
          value: 0.4,
          coefficient: 1,
          operation: "add",
        },
      ],
      clamp: null,
    });

    expect(request).toEqual({
      method: "additive",
      method_version: "demo.v1",
      terms: [
        {
          id: "base",
          label: "Base",
          value: 0.4,
          coefficient: 1,
          operation: "add",
          interval: null,
        },
      ],
      clamp: null,
      intercept: 0,
    });
  });

  it.each([
    [
      "unknown field",
      { ...weightedInput(), secret: "DO_NOT_LEAK" },
      "assay.unknown_field",
    ],
    [
      "missing field",
      { method: "weighted_mean", components: [], clamp: "reject" },
      "assay.missing_field",
    ],
    [
      "unknown method",
      { ...weightedInput(), method: "median" },
      "assay.invalid_method",
    ],
    [
      "boolean number",
      {
        ...weightedInput(),
        components: [
          {
            ...(
              weightedInput().components as ReadonlyArray<
                Record<string, unknown>
              >
            )[0],
            value: true,
          },
        ],
      },
      "assay.invalid_number",
    ],
    [
      "unsafe integer",
      {
        ...weightedInput(),
        components: [
          {
            ...(
              weightedInput().components as ReadonlyArray<
                Record<string, unknown>
              >
            )[0],
            value: Number.MAX_SAFE_INTEGER + 1,
          },
        ],
      },
      "assay.invalid_number",
    ],
    [
      "invalid Unicode scalar",
      {
        ...weightedInput(),
        components: [
          {
            ...(
              weightedInput().components as ReadonlyArray<
                Record<string, unknown>
              >
            )[0],
            label: "DO_NOT_LEAK\ud800",
          },
        ],
      },
      "assay.invalid_text",
    ],
    [
      "missing weight",
      {
        ...weightedInput(),
        components: [
          {
            ...(
              weightedInput().components as ReadonlyArray<
                Record<string, unknown>
              >
            )[0],
            weight: null,
          },
        ],
      },
      "assay.missing_weight",
    ],
    [
      "duplicate id",
      {
        ...weightedInput(),
        components: [
          ...(weightedInput().components as ReadonlyArray<
            Record<string, unknown>
          >),
          ...(weightedInput().components as ReadonlyArray<
            Record<string, unknown>
          >),
        ],
      },
      "assay.duplicate_identifier",
    ],
    [
      "out of range",
      {
        ...weightedInput(),
        components: [
          {
            ...(
              weightedInput().components as ReadonlyArray<
                Record<string, unknown>
              >
            )[0],
            value: 11,
          },
        ],
      },
      "assay.out_of_range",
    ],
  ])("rejects %s without echoing caller values", (_name, input, code) => {
    const error = errorFrom(() => parseRequest(input));

    expect(error.message).toBe(code);
    expect(error.code).toBe(code);
    expect(error.message).not.toContain("DO_NOT_LEAK");
  });

  it("rejects malformed JSON with a stable value-free code", () => {
    expectCode(() => parseRequestJson('{"method":'), "assay.invalid_contract");
  });
});

describe("parseScoreResult", () => {
  it("parses a coherent result from JSON and freezes nested rows", () => {
    const result = parseScoreResultJson(JSON.stringify(weightedResult()));

    expect(result).toEqual(weightedResult());
    expect(Object.isFrozen(result)).toBe(true);
    expect(Object.isFrozen(result.components[0])).toBe(true);
  });

  it("rejects method-incoherent forged results", () => {
    const forged = { ...weightedResult(), score: 0.75 };

    expectCode(() => parseScoreResult(forged), "assay.invalid_result");
  });

  it("rejects unknown result fields and invalid hashes", () => {
    expectCode(
      () => parseScoreResult({ ...weightedResult(), unexpected: true }),
      "assay.unknown_field",
    );
    expectCode(
      () =>
        parseScoreResult({ ...weightedResult(), inputs_hash: "DO_NOT_LEAK" }),
      "assay.invalid_inputs_hash",
    );
  });
});
