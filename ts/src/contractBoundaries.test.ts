import { readFileSync } from "node:fs";

import { describe, expect, it } from "vitest";

import { parseRequest, parseRequestJson, parseScoreResult } from "./index.js";

interface Vector {
  readonly id: string;
  readonly expected: Readonly<Record<string, unknown>>;
}

function vectors(): ReadonlyArray<Vector> {
  const path = new URL(
    "../../testdata/vectors/composition.json",
    import.meta.url,
  );
  return JSON.parse(readFileSync(path, "utf8")) as ReadonlyArray<Vector>;
}

function component(): Record<string, unknown> {
  return {
    id: "quality",
    label: "Quality",
    value: 0.5,
    scale: { minimum: 0, maximum: 1, direction: "higher_is_better" },
    weight: 1,
  };
}

function weighted(
  overrides: Record<string, unknown> = {},
): Record<string, unknown> {
  return {
    method: "weighted_mean",
    method_version: "demo.v1",
    components: [component()],
    clamp: "reject",
    ...overrides,
  };
}

function expectCode(action: () => unknown, code: string): void {
  expect(action).toThrow(code);
  try {
    action();
  } catch (error: unknown) {
    expect(error).toMatchObject({ code });
  }
}

describe("request boundary mutations", () => {
  it.each([
    [null, "assay.invalid_method"],
    [weighted({ components: {} }), "assay.invalid_contract"],
    [
      weighted({ components: [{ ...component(), scale: null }] }),
      "assay.invalid_object",
    ],
    [weighted({ components: [] }), "assay.empty_components"],
    [
      {
        method: "minimum",
        method_version: "demo.v1",
        components: [],
        clamp: "reject",
      },
      "assay.empty_components",
    ],
    [
      {
        method: "additive",
        method_version: "demo.v1",
        terms: [],
        clamp: null,
      },
      "assay.empty_terms",
    ],
  ])("rejects malformed container %#", (input, code) => {
    expectCode(() => parseRequest(input), code);
  });

  it.each([
    ["id", 1, "assay.invalid_identifier"],
    ["id", "Bad", "assay.invalid_identifier"],
    ["id", `a${"b".repeat(128)}`, "assay.invalid_identifier"],
    ["label", "   ", "assay.invalid_label"],
    ["label", "x".repeat(257), "assay.invalid_label"],
    ["label", "\udc00", "assay.invalid_text"],
    ["weight", 0, "assay.invalid_weight"],
  ])("rejects invalid component %s", (field, value, code) => {
    const input = weighted({
      components: [{ ...component(), [field]: value }],
    });
    expectCode(() => parseRequest(input), code);
  });

  it.each([
    [
      {
        ...component(),
        scale: { minimum: 1, maximum: 1, direction: "higher_is_better" },
      },
      "assay.invalid_scale",
    ],
    [
      {
        ...component(),
        scale: { minimum: 0, maximum: 1, direction: "sideways" },
      },
      "assay.invalid_direction",
    ],
    [
      { ...component(), interval: { low: 0.5, high: 0.5 } },
      "assay.invalid_interval",
    ],
  ])("rejects invalid scale or interval %#", (invalid, code) => {
    expectCode(() => parseRequest(weighted({ components: [invalid] })), code);
  });

  it("rejects invalid clamp and additive operation enums", () => {
    expectCode(
      () => parseRequest(weighted({ clamp: "sometimes" })),
      "assay.invalid_clamp_policy",
    );
    expectCode(
      () =>
        parseRequest({
          method: "additive",
          method_version: "demo.v1",
          terms: [
            {
              id: "term",
              label: "Term",
              value: 1,
              coefficient: 1,
              operation: "multiply",
            },
          ],
          clamp: null,
        }),
      "assay.invalid_operation",
    );
  });

  it("accepts valid scalar pairs and a null-prototype root", () => {
    const input = Object.assign(
      Object.create(null) as Record<string, unknown>,
      weighted({ components: [{ ...component(), label: "😀" }] }),
    );

    expect(parseRequest(input).method).toBe("weighted_mean");
  });

  it("refuses a non-string JSON boundary value at runtime", () => {
    expectCode(
      () => parseRequestJson(1 as unknown as string),
      "assay.invalid_contract",
    );
  });
});

describe("result replay mutations", () => {
  it("rejects schema, empty-row, and selected-id shape mutations", () => {
    const source = vectors()[0]?.expected;
    if (source === undefined) throw new Error("missing weighted vector");

    expectCode(
      () => parseScoreResult({ ...source, schema: "assay.result/v2" }),
      "assay.invalid_contract",
    );
    expectCode(
      () => parseScoreResult({ ...source, components: [] }),
      "assay.empty_components",
    );
    expectCode(
      () => parseScoreResult({ ...source, selected_component_id: "Bad" }),
      "assay.invalid_identifier",
    );
  });

  it("rejects weighted metadata, row, score, and interval mutations", () => {
    const source = vectors()[0]?.expected;
    if (source === undefined) throw new Error("missing weighted vector");
    const rows = source.components as ReadonlyArray<Record<string, unknown>>;

    for (const forged of [
      { ...source, weight_total: 99 },
      { ...source, intercept: 0 },
      { ...source, score: 0 },
      { ...source, interval: { low: 0.1, high: 0.2 } },
      {
        ...source,
        components: [{ ...rows[0], normalized: null }, ...rows.slice(1)],
      },
      {
        ...source,
        components: [{ ...rows[0], coefficient: 0.5 }, ...rows.slice(1)],
      },
    ]) {
      expectCode(() => parseScoreResult(forged), "assay.invalid_result");
    }
  });

  it("rejects additive and minimum replay mutations", () => {
    const all = vectors();
    const additive = all.find(
      (vector) => vector.id === "edgereco_recommendation",
    )?.expected;
    const minimum = all.find(
      (vector) => vector.id === "almamesh_domain_strength_forward_tie",
    )?.expected;
    if (additive === undefined || minimum === undefined)
      throw new Error("missing vectors");

    expectCode(
      () =>
        parseScoreResult({ ...additive, selected_component_id: "relevance" }),
      "assay.invalid_result",
    );
    expectCode(
      () => parseScoreResult({ ...additive, score: 0 }),
      "assay.invalid_result",
    );
    expectCode(
      () => parseScoreResult({ ...minimum, selected_component_id: "sav_pct" }),
      "assay.invalid_result",
    );
    expectCode(
      () => parseScoreResult({ ...minimum, interval: { low: 0.1, high: 0.2 } }),
      "assay.invalid_result",
    );
  });
});
