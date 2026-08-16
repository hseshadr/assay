import { readFile } from "node:fs/promises";

import { describe, expect, it } from "vitest";

import {
  compose,
  parseRequest,
  parseScoreResult,
  parseScoreResultJson,
} from "./index.js";
import { inputsHash, inputsPreimage } from "./requestHash.js";

interface CompositionVector {
  readonly id: string;
  readonly request: unknown;
  readonly expected: Readonly<Record<string, unknown>>;
}

const EXPECTED_IDS = [
  "northstar_uncapped_weighted",
  "edgereco_recommendation",
  "amlfilter_match_confidence",
  "almamesh_domain_strength_forward_tie",
  "almamesh_domain_strength_reverse_tie",
] as const;

const EXPECTED_HASHES = {
  northstar_uncapped_weighted:
    "sha256:0266b1c59c97bacf85dc945685c55bb4386856b525249c7d5663a8edf020ba06",
  edgereco_recommendation:
    "sha256:df9b86d02e3cabea42e98ef18df165f6f8a227f8f144ae430496a43b5fcdc5fb",
  amlfilter_match_confidence:
    "sha256:64cecab703da9d0f2a473ad4a14c4ccb96b683d9b20169d1dcd650892eba0ff6",
  almamesh_domain_strength_forward_tie:
    "sha256:c1dd2da5ebd54dfcc6f3b250f118ce1fc6ce7f3dfc7d249cf7a5f7216d4eaa5e",
  almamesh_domain_strength_reverse_tie:
    "sha256:09c0694100a04d66119ca5712cb669459e7bece368e36f729d2bb1c98f4f1115",
} as const;

const BINARY64_REQUEST_JSON =
  '{"method":"additive","method_version":"binary64.v1","terms":[{"id":"two53","label":"2^53","value":9007199254740992,"coefficient":0,"operation":"add"},{"id":"two53_plus_one","label":"2^53 + 1 literal","value":9007199254740993,"coefficient":0,"operation":"add"},{"id":"next_binary64","label":"Next binary64","value":9007199254740994,"coefficient":0,"operation":"add"},{"id":"large","label":"Large","value":1e20,"coefficient":0,"operation":"add"},{"id":"near_max","label":"Near max","value":1e308,"coefficient":0,"operation":"add"}],"clamp":null}';
const BINARY64_PREIMAGE =
  '["assay.request/v1","additive","binary64.v1",null,"f64:0000000000000000",[["two53","2^53","f64:4340000000000000","f64:0000000000000000","add",null],["two53_plus_one","2^53 + 1 literal","f64:4340000000000000","f64:0000000000000000","add",null],["next_binary64","Next binary64","f64:4340000000000001","f64:0000000000000000","add",null],["large","Large","f64:4415af1d78b58c40","f64:0000000000000000","add",null],["near_max","Near max","f64:7fe1ccf385ebc8a0","f64:0000000000000000","add",null]]]';
const BINARY64_HASH =
  "sha256:06bdaca8183f904e058025140da6166e9e0ea4abacc170129c0685cb579fd010";

async function vectors(): Promise<ReadonlyArray<CompositionVector>> {
  const path = new URL(
    "../../testdata/vectors/composition.json",
    import.meta.url,
  );
  const text = await readFile(path, "utf8");
  return JSON.parse(text) as ReadonlyArray<CompositionVector>;
}

describe("shared Python and TypeScript composition parity", () => {
  it("executes every named vector with byte-equivalent result JSON", async () => {
    const cases = await vectors();
    expect(cases.map((vector) => vector.id)).toEqual(EXPECTED_IDS);

    const executed = new Set<string>();
    for (const vector of cases) {
      const result = compose(parseRequest(vector.request));
      expect(JSON.stringify(result), vector.id).toBe(
        JSON.stringify(vector.expected),
      );
      expect(result.inputs_hash, vector.id).toBe(
        EXPECTED_HASHES[vector.id as keyof typeof EXPECTED_HASHES],
      );
      expect(parseScoreResultJson(JSON.stringify(result))).toEqual(result);
      executed.add(vector.id);
    }

    expect([...executed]).toEqual(EXPECTED_IDS);
  });

  it("replays each result method and rejects forged method metadata", async () => {
    const cases = await vectors();
    for (const vector of cases) {
      const method = vector.expected.method as Readonly<
        Record<string, unknown>
      >;
      const forged = {
        ...vector.expected,
        method: {
          ...method,
          id: method.id === "minimum" ? "additive" : "minimum",
        },
      };

      expect(() => parseScoreResult(forged), vector.id).toThrow(
        "assay.invalid_result",
      );
    }
  });

  it("hashes declared field and component order while canonicalizing signed zero", async () => {
    const [weighted] = await vectors();
    if (weighted === undefined) throw new Error("missing weighted vector");
    const request = weighted.request as Readonly<Record<string, unknown>>;
    const components = request.components as ReadonlyArray<
      Record<string, unknown>
    >;
    const changedLabel = {
      ...request,
      components: [
        { ...components[0], label: "Changed" },
        ...components.slice(1),
      ],
    };
    const reversed = { ...request, components: [...components].reverse() };
    const baseHash = compose(parseRequest(request)).inputs_hash;

    expect(compose(parseRequest(changedLabel)).inputs_hash).not.toBe(baseHash);
    expect(compose(parseRequest(reversed)).inputs_hash).not.toBe(baseHash);

    const negativeZero = {
      ...request,
      components: [{ ...components[0], value: -0 }, ...components.slice(1)],
    };
    const positiveZero = {
      ...request,
      components: [{ ...components[0], value: 0 }, ...components.slice(1)],
    };
    expect(compose(parseRequest(negativeZero)).inputs_hash).toBe(
      compose(parseRequest(positiveZero)).inputs_hash,
    );
  });

  it("clamps additive output only after every ordered contribution", () => {
    const request = parseRequest({
      method: "additive",
      method_version: "clamp.v1",
      intercept: 0.9,
      terms: [
        {
          id: "boost",
          label: "Boost",
          value: 0.4,
          coefficient: 1,
          operation: "add",
        },
        {
          id: "penalty",
          label: "Penalty",
          value: 0.2,
          coefficient: 1,
          operation: "subtract",
        },
      ],
      clamp: "clamp",
    });

    expect(compose(request).score).toBe(1);
  });

  it("matches Python binary64 bits and hash above the safe-integer range", () => {
    const request = parseRequest(JSON.parse(BINARY64_REQUEST_JSON) as unknown);

    expect(inputsPreimage(request)).toBe(BINARY64_PREIMAGE);
    expect(inputsHash(request)).toBe(BINARY64_HASH);
    expect(compose(request).inputs_hash).toBe(BINARY64_HASH);
  });
});
