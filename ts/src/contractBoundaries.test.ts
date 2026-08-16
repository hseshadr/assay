import { readFileSync } from "node:fs";

import { describe, expect, it, vi } from "vitest";

import {
  ContractCode,
  ContractValidationError,
  compose,
  parseRequest,
  parseRequestJson,
  parseScoreResult,
  type WeightedMeanRequest,
  weightedMean,
} from "./index.js";

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

function expectPrivateCode(
  action: () => unknown,
  code = "assay.invalid_object",
): void {
  try {
    action();
  } catch (error: unknown) {
    expect(error).toMatchObject({ code, message: code });
    expect(String(error)).not.toMatch(/PII_(?:GETTER|PROXY|DESCRIPTOR)/u);
    return;
  }
  throw new Error("expected a private contract error");
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

  it("rejects symbols, non-enumerable fields, accessors, and custom prototypes", () => {
    const symbolRoot = weighted();
    Object.defineProperty(symbolRoot, Symbol("PII_SYMBOL"), {
      enumerable: true,
      value: "private",
    });
    expectPrivateCode(() => parseRequest(symbolRoot));

    const hidden = component();
    Object.defineProperty(hidden, "PII_HIDDEN", {
      enumerable: false,
      value: "private",
    });
    expectPrivateCode(() => parseRequest(weighted({ components: [hidden] })));

    const accessor = component();
    Object.defineProperty(accessor, "value", {
      enumerable: true,
      get: () => {
        throw new Error("PII_GETTER");
      },
    });
    expectPrivateCode(() => parseRequest(weighted({ components: [accessor] })));

    expectPrivateCode(() =>
      parseRequest(
        Object.assign(Object.create({ inherited: true }), weighted()),
      ),
    );

    const nestedPrototype = component();
    nestedPrototype.scale = Object.assign(
      Object.create({ inherited: true }),
      nestedPrototype.scale,
    );
    expectPrivateCode(() =>
      parseRequest(weighted({ components: [nestedPrototype] })),
    );
  });

  it("translates hostile proxy reflection failures without leaking values", () => {
    const prototypeFailure = new Proxy(weighted(), {
      getPrototypeOf: () => {
        throw new Error("PII_PROXY");
      },
    });
    expectPrivateCode(() => parseRequest(prototypeFailure));

    const descriptorFailure = new Proxy(weighted(), {
      getOwnPropertyDescriptor: () => {
        throw new Error("PII_DESCRIPTOR");
      },
    });
    expectPrivateCode(() => parseRequest(descriptorFailure));

    const keysFailure = new Proxy(weighted(), {
      ownKeys: () => {
        throw new Error("PII_PROXY");
      },
    });
    expectPrivateCode(() => parseRequest(keysFailure));

    const disguisedFailure = new Proxy(weighted(), {
      getPrototypeOf: () => {
        throw new ContractValidationError(ContractCode.INVALID_WEIGHT);
      },
    });
    expectPrivateCode(() => parseRequest(disguisedFailure));
  });

  it("reads data descriptors without invoking getters or proxy get traps", () => {
    let getterCalls = 0;
    const accessor = weighted();
    Object.defineProperty(accessor, "method", {
      enumerable: true,
      get: () => {
        getterCalls += 1;
        throw new Error("PII_GETTER");
      },
    });
    expectPrivateCode(() => parseRequest(accessor));
    expect(getterCalls).toBe(0);

    let getCalls = 0;
    const proxy = new Proxy(weighted(), {
      get: () => {
        getCalls += 1;
        throw new Error("PII_PROXY");
      },
    });
    expect(parseRequest(proxy).method).toBe("weighted_mean");
    expect(getCalls).toBe(0);
  });

  it("rejects sparse, extended, and custom-prototype arrays", () => {
    const sparse = new Array<Record<string, unknown>>(1);
    expectPrivateCode(() => parseRequest(weighted({ components: sparse })));

    const extended = [component()];
    Object.assign(extended, { PII_EXTRA: "private" });
    expectPrivateCode(() => parseRequest(weighted({ components: extended })));

    const custom = [component()];
    Object.setPrototypeOf(custom, Object.create(Array.prototype));
    expectPrivateCode(() => parseRequest(weighted({ components: custom })));

    let indexGetterCalls = 0;
    const accessor = [component()];
    Object.defineProperty(accessor, "0", {
      enumerable: true,
      get: () => {
        indexGetterCalls += 1;
        throw new Error("PII_GETTER");
      },
    });
    expectPrivateCode(() => parseRequest(weighted({ components: accessor })));
    expect(indexGetterCalls).toBe(0);

    const symbol = [component()];
    Object.defineProperty(symbol, Symbol("PII_SYMBOL"), {
      enumerable: true,
      value: "private",
    });
    expectPrivateCode(() => parseRequest(weighted({ components: symbol })));
  });

  it("checks dense array membership in one pass", () => {
    const count = 4096;
    const components = Array.from({ length: count }, (_, index) => ({
      ...component(),
      id: `quality_${index}`,
    }));
    const originalIncludes = Array.prototype.includes;
    let repeatedKeyScans = 0;
    const includes = vi
      .spyOn(Array.prototype, "includes")
      .mockImplementation(function (
        this: unknown[],
        searchElement: unknown,
        fromIndex?: number,
      ): boolean {
        if (this.length === count + 1 && this[this.length - 1] === "length") {
          repeatedKeyScans += 1;
        }
        return Reflect.apply(originalIncludes, this, [
          searchElement,
          fromIndex,
        ]);
      });

    try {
      const parsed = parseRequest(weighted({ components }));
      if (parsed.method === "additive") throw new Error("wrong request");
      expect(parsed.components).toHaveLength(count);
      expect(repeatedKeyScans).toBe(0);
    } finally {
      includes.mockRestore();
    }
  });

  it("rejects request intervals that do not contain their point", () => {
    const payloads = [
      weighted({
        components: [
          { ...component(), value: 0.5, interval: { low: 0.1, high: 0.2 } },
        ],
      }),
      {
        method: "minimum",
        method_version: "demo.v1",
        components: [
          {
            ...component(),
            value: 0.5,
            interval: { low: 0.1, high: 0.2 },
            weight: null,
          },
        ],
        clamp: "reject",
      },
      {
        method: "additive",
        method_version: "demo.v1",
        terms: [
          {
            id: "quality",
            label: "Quality",
            value: 0.5,
            coefficient: 1,
            operation: "add",
            interval: { low: 0.1, high: 0.2 },
          },
        ],
        clamp: null,
      },
    ];

    for (const payload of payloads) {
      expectCode(() => parseRequest(payload), "assay.invalid_interval");
      expectCode(
        () => parseRequestJson(JSON.stringify(payload)),
        "assay.invalid_interval",
      );
    }

    const copied = structuredClone(
      weighted({
        components: [
          { ...component(), value: 0.5, interval: { low: 0.4, high: 0.6 } },
        ],
      }),
    );
    const copiedRows = copied.components as Array<Record<string, unknown>>;
    const copiedFirst = copiedRows[0];
    if (copiedFirst === undefined) throw new Error("missing copied row");
    copiedFirst.value = 0.9;
    expectCode(() => parseRequest(copied), "assay.invalid_interval");
    expectCode(
      () => weightedMean(copied as unknown as WeightedMeanRequest),
      "assay.invalid_interval",
    );
  });

  it("composes every method when each interval contains its point", () => {
    const requests = [
      weighted({
        components: [
          { ...component(), value: 0.5, interval: { low: 0.4, high: 0.6 } },
        ],
      }),
      {
        method: "minimum",
        method_version: "demo.v1",
        components: [
          {
            ...component(),
            value: 0.5,
            interval: { low: 0.4, high: 0.6 },
            weight: null,
          },
        ],
        clamp: "reject",
      },
      {
        method: "additive",
        method_version: "demo.v1",
        terms: [
          {
            id: "quality",
            label: "Quality",
            value: 0.5,
            coefficient: 1,
            operation: "add",
            interval: { low: 0.4, high: 0.6 },
          },
        ],
        clamp: null,
      },
    ];

    for (const request of requests) {
      expect(compose(parseRequest(request)).components).toHaveLength(1);
    }
  });

  it("takes a detached snapshot and rejects a shape that mutates during reflection", () => {
    const input = weighted();
    const parsed = parseRequest(input);
    if (parsed.method === "additive") throw new Error("wrong request");
    const sourceRows = input.components as Array<Record<string, unknown>>;
    const parsedRows = parsed.components;
    const first = sourceRows[0];
    if (first === undefined) throw new Error("missing source component");
    first.label = "Mutated";
    sourceRows.push(component());

    expect(parsedRows).toHaveLength(1);
    expect(parsedRows[0]?.label).toBe("Quality");

    let reads = 0;
    const changing = new Proxy(weighted(), {
      ownKeys: (target) => {
        reads += 1;
        return reads === 1
          ? Reflect.ownKeys(target)
          : [...Reflect.ownKeys(target), "PII_MUTATED"];
      },
    });
    expectPrivateCode(() => parseRequest(changing));
  });

  it("rejects root and nested cycles with a stable value-free code", () => {
    const root = weighted();
    root.self = root;
    expectPrivateCode(() => parseRequest(root));

    const nested = component();
    const scale = nested.scale as Record<string, unknown>;
    scale.self = nested;
    expectPrivateCode(() => parseRequest(weighted({ components: [nested] })));
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

  it("applies the same redacted descriptor boundary to result objects", () => {
    const source = vectors()[0]?.expected;
    if (source === undefined) throw new Error("missing weighted vector");
    let getterCalls = 0;
    const accessor = { ...source };
    Object.defineProperty(accessor, "score", {
      enumerable: true,
      get: () => {
        getterCalls += 1;
        throw new Error("PII_GETTER");
      },
    });

    expectPrivateCode(() => parseScoreResult(accessor));
    expect(getterCalls).toBe(0);

    const nested = structuredClone(source);
    const rows = nested.components as Array<Record<string, unknown>>;
    Object.defineProperty(rows[0], "PII_HIDDEN", {
      enumerable: false,
      value: "private",
    });
    expectPrivateCode(() => parseScoreResult(nested));

    const reflected = new Proxy(source, {
      ownKeys: () => {
        throw new Error("PII_PROXY");
      },
    });
    expectPrivateCode(() => parseScoreResult(reflected));
  });

  it("detaches parsed results from immediate and queued source mutation", async () => {
    const source = structuredClone(vectors()[0]?.expected) as
      | Record<string, unknown>
      | undefined;
    if (source === undefined) throw new Error("missing weighted vector");
    const parsed = parseScoreResult(source);
    const sourceRows = source.components as Array<Record<string, unknown>>;

    source.score = 0;
    queueMicrotask(() => {
      const first = sourceRows[0];
      if (first !== undefined) first.contribution = 0;
    });
    await Promise.resolve();

    expect(parsed.score).toBe(0.92);
    expect(parsed.components[0]?.contribution).toBe(0.19);
    expect(Object.isFrozen(parsed.components)).toBe(true);
  });
});
