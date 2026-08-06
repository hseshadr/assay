/**
 * The ranking face, pinned to hand-computed worked examples.
 *
 * Every expected number in this file was computed by hand from the metric's
 * definition (the `// hand:` comments show the arithmetic), never read back out of
 * the code under test. A test that asserts what the implementation happens to
 * return measures shape, not property, and would stay green through the exact bugs
 * this module exists to catch.
 *
 * The same numbers are asserted against the *Python* implementation by the shared
 * vectors in `metricVectors.test.ts` / `tests/test_metric_vectors.py`. This file is
 * the per-property guard set the mutation harness breaks one at a time.
 */

import { describe, expect, it } from "vitest";
import {
  binaryJudgments,
  f1AtK,
  type Judgments,
  mrr,
  precisionAtK,
  recallAtK,
} from "./ranking.js";
import {
  AssayError,
  EmptyRelevantSet,
  InvalidRankingRequest,
} from "./scoringErrors.js";

// Four judged-relevant documents; the ranker returned five, hitting at positions 1, 3, 5.
const RELEVANT: Judgments = binaryJudgments(["d1", "d3", "d5", "d9"]);
const RANKED = ["d1", "d2", "d3", "d4", "d5"];

describe("precision@k", () => {
  it("counts hits over k", () => {
    // Given five ranked documents with relevant ones at positions 1, 3 and 5
    // When precision is taken at 3 and at 5
    // Then it is the hit count over k
    expect(precisionAtK(RELEVANT, RANKED, 3)).toBeCloseTo(2 / 3, 15); // hand: {d1,d3}/3
    expect(precisionAtK(RELEVANT, RANKED, 5)).toBeCloseTo(3 / 5, 15); // hand: {d1,d3,d5}/5
  });

  it("charges for the empty positions when k exceeds the list", () => {
    // Given a ranker that returned only 5 documents
    // When precision is taken at 10
    // Then the denominator is k, never the list length — returning less must not
    // buy a better score
    expect(precisionAtK(RELEVANT, RANKED, 10)).toBeCloseTo(3 / 10, 15); // hand: NOT 3/5
  });

  it("scores only the top-k slice, so order changes the answer", () => {
    // Given the same five documents with the two hits pushed to the back
    const reordered = ["d2", "d4", "d1", "d3", "d5"];
    // When precision is taken at 2
    // Then it is 0 — the identical retrieved SET scores differently by position alone
    expect(precisionAtK(RELEVANT, reordered, 2)).toBe(0); // hand: {}/2
    expect(precisionAtK(RELEVANT, RANKED, 2)).toBeCloseTo(1 / 2, 15); // hand: {d1}/2
  });
});

describe("recall@k", () => {
  it("divides by the relevant set, never by k", () => {
    // Given four judged-relevant documents, of which the top 3 hold two
    // When recall is taken at 3 and at 5
    // Then the denominator is the size of the relevant set (4), never k
    expect(recallAtK(RELEVANT, RANKED, 3)).toBeCloseTo(2 / 4, 15); // hand: 0.5, NOT 2/3
    expect(recallAtK(RELEVANT, RANKED, 5)).toBeCloseTo(3 / 4, 15); // hand: 0.75, NOT 3/5
  });

  it("stays separate from precision when the relevant set is larger than k", () => {
    // Given 10 relevant documents and a ranker that returned 2, both relevant
    const relevant = binaryJudgments(
      Array.from({ length: 10 }, (_, i) => `r${i}`),
    );
    // When both are measured at 2
    // Then precision is perfect and recall is not — the two must not collapse
    expect(precisionAtK(relevant, ["r0", "r1"], 2)).toBe(1);
    expect(recallAtK(relevant, ["r0", "r1"], 2)).toBeCloseTo(0.2, 15); // hand: 2/10
  });
});

describe("F1@k", () => {
  it("takes the harmonic mean, not the average", () => {
    // Given precision 0.6 and recall 0.75 at k = 5
    // When F1 is taken
    // Then it is 2pr/(p+r), which sits below the arithmetic mean 0.675
    const expected = (2 * 0.6 * 0.75) / (0.6 + 0.75); // hand: 0.9 / 1.35
    expect(f1AtK(RELEVANT, RANKED, 5)).toBeCloseTo(expected, 15);
    expect(f1AtK(RELEVANT, RANKED, 5)).toBeCloseTo(0.6666666666666666, 15);
  });

  it("reports zero, not NaN, when nothing relevant is retrieved", () => {
    // Given a ranked list holding none of the relevant documents
    // When F1 is taken, so precision and recall are both 0
    // Then the 0/0 branch returns 0 rather than propagating NaN downstream
    expect(f1AtK(RELEVANT, ["x", "y"], 2)).toBe(0);
  });
});

describe("reciprocal rank", () => {
  it("reports the reciprocal of the FIRST hit position", () => {
    // Given a list whose first relevant document sits third
    // When the reciprocal rank is taken
    // Then it is 1/3, and positions are 1-based
    expect(mrr(binaryJudgments(["x3"]), ["x1", "x2", "x3", "x4"])).toBeCloseTo(
      1 / 3,
      15,
    ); // hand: 1/3
  });

  it("uses the first hit and not the last when there are several", () => {
    // Given hits at positions 1 and 3
    // When the reciprocal rank is taken
    // Then it is 1/1 — a later hit must not displace the earlier one
    expect(mrr(RELEVANT, RANKED)).toBe(1); // hand: 1/1, NOT 1/3
  });

  it("reports a real zero when the list holds no relevant document", () => {
    // Given a ranker that returned nothing relevant, with judgments that do exist
    // When the reciprocal rank is taken
    // Then it is 0.0 — the ranker missed, which is different from nobody judging
    expect(mrr(RELEVANT, ["x", "y"])).toBe(0);
  });

  it("is untruncated, so a deep hit scores small rather than zero", () => {
    // Given the only relevant document at position 40
    const ranked = Array.from({ length: 40 }, (_, i) => `d${i}`);
    // When the reciprocal rank is taken
    // Then it is 1/40 — no cut-off silently rounds a deep hit down to a miss
    expect(mrr(binaryJudgments(["d39"]), ranked)).toBeCloseTo(1 / 40, 15);
  });
});

describe("graded relevance", () => {
  it("treats a judged gain of zero as NOT relevant", () => {
    // Given four judged documents, one of them graded 0
    const graded: Judgments = { a: 3, b: 2, c: 1, d: 0 };
    // When the ranker returns d first and c second
    // Then d is a miss and the relevant set is {a,b,c}, of size 3
    expect(precisionAtK(graded, ["d", "c", "a", "e"], 2)).toBe(0.5); // hand: {c}/2
    expect(recallAtK(graded, ["d", "c", "a", "e"], 2)).toBeCloseTo(1 / 3, 15); // hand: {c}/3
    expect(mrr(graded, ["d", "c", "a", "e"])).toBe(0.5); // hand: first hit c, rank 2
  });

  it("treats an unjudged document as not relevant", () => {
    // Given judgments that mention only d1
    // When the ranker returns two documents nobody judged alongside it
    // Then the unjudged ones count as misses, not as unknowns
    expect(precisionAtK({ d1: 1 }, ["zz", "d1", "yy"], 3)).toBeCloseTo(
      1 / 3,
      15,
    );
  });

  it("does not resolve a document id off the prototype chain", () => {
    // Given judgments that never mention "constructor"
    // When a ranked list contains it
    // Then it is a miss — a bare index read would hand back Object's constructor
    expect(precisionAtK({ d1: 1 }, ["constructor", "d1"], 2)).toBe(0.5);
  });
});

describe("refusals", () => {
  function expectCode(call: () => unknown, code: string): void {
    // The `toThrow` assertion is what guarantees the catch below actually runs; a
    // bare try/catch would pass silently if the call returned a number instead.
    expect(call).toThrow(AssayError);
    try {
      call();
    } catch (err) {
      expect((err as AssayError).code).toBe(code);
    }
  }

  it("refuses when no document is judged relevant", () => {
    // Given judgments where every gain is 0
    // When any metric is taken
    // Then it refuses rather than returning 0.0, which would blame the ranker for
    // missing judgments
    expect(() => precisionAtK({ d1: 0 }, ["d1"], 1)).toThrow(EmptyRelevantSet);
    expect(() => mrr({ d1: 0 }, ["d1"])).toThrow(EmptyRelevantSet);
    expectCode(
      () => recallAtK({ d1: 0 }, ["d1"], 1),
      "assay.empty_relevant_set",
    );
  });

  it("refuses a fractional relevance gain rather than rounding it", () => {
    // Given a gain of 2.5
    // When scored
    // Then it refuses — rounding it would move the document across the relevant
    // boundary and no reference semantics says which way
    expect(() => precisionAtK({ d1: 2.5 }, ["d1"], 1)).toThrow(
      InvalidRankingRequest,
    );
  });

  it("refuses a negative relevance gain", () => {
    // Given a gain below zero
    // When scored
    // Then it refuses — a grade is a level, and there is none below not-relevant
    expectCode(
      () => precisionAtK({ d1: -1 }, ["d1"], 1),
      "assay.invalid_ranking_request",
    );
  });

  it("refuses a ranked list holding the same document twice", () => {
    // Given a duplicate in the ranked list
    // When scored
    // Then it refuses rather than de-duplicating, which would move every position
    expect(() => precisionAtK(RELEVANT, ["d1", "d1"], 2)).toThrow(
      InvalidRankingRequest,
    );
  });

  it("refuses an empty ranked list", () => {
    // Given a ranker that returned nothing at all
    // When scored
    // Then it refuses — there is nothing to score, which is not the same as a miss
    expect(() => precisionAtK(RELEVANT, [], 3)).toThrow(InvalidRankingRequest);
    expect(() => mrr(RELEVANT, [])).toThrow(InvalidRankingRequest);
  });

  it("refuses a k that is not a positive whole number", () => {
    // Given k of 0, a negative k, and a fractional k
    // When scored
    // Then each refuses. Python declares `k: int` and mypy --strict enforces it at
    // the call site; TypeScript's `number` cannot, so it is checked here instead.
    expect(() => precisionAtK(RELEVANT, RANKED, 0)).toThrow(
      InvalidRankingRequest,
    );
    expect(() => precisionAtK(RELEVANT, RANKED, -1)).toThrow(
      InvalidRankingRequest,
    );
    expect(() => precisionAtK(RELEVANT, RANKED, 2.5)).toThrow(
      InvalidRankingRequest,
    );
    expect(() => recallAtK(RELEVANT, RANKED, 0)).toThrow(InvalidRankingRequest);
  });
});

describe("binaryJudgments", () => {
  it("gives every listed document a gain of 1", () => {
    // Given a relevant set expressed as bare ids
    // When it is turned into judgments
    // Then each carries gain 1, which is the graded form of "relevant"
    expect(binaryJudgments(["a", "b"])).toEqual({ a: 1, b: 1 });
  });

  it("keeps a document literally called __proto__", () => {
    // Given a document id that collides with JavaScript's prototype accessor
    const judgments = binaryJudgments(["__proto__", "ok"]);
    // When the judgments are inspected
    // Then it is a real own key with gain 1. On a plain object it would not be:
    // `plain["__proto__"] = 1` invokes Object.prototype's setter, which ignores a
    // non-object value, and the document silently disappears. Python keeps it, so
    // this scored precision@1 as 1.0 in Python and 0 in the browser — no refusal in
    // either language, just two different answers.
    expect(Object.keys(judgments)).toEqual(["__proto__", "ok"]);
    expect(Object.hasOwn(judgments, "__proto__")).toBe(true);
    expect(precisionAtK(judgments, ["__proto__"], 1)).toBe(1); // hand: {__proto__}/1
  });
});
