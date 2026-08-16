/**
 * Shared metric vectors: the cross-language ANSWER contract.
 *
 * This replays `testdata/vectors/metrics.json` — the same file, case for case, that
 * `tests/test_metric_vectors.py` replays against the Python face. Python delegates
 * to `trec_eval` (through `ir_measures`) and scikit-learn; this package counts the
 * same quantities out against their definitions. Two implementations of one rule is
 * exactly the arrangement that drifts, so both are pinned to a single set of
 * hand-computed answers. A divergence fails CI in both languages rather than being
 * discovered later by a human.
 *
 * Every number in that file was computed from the metric's definition (each case
 * carries its arithmetic in a `hand` field) and never read back out of either
 * implementation.
 */

import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";
import { AssayError, InvalidScoreRequest } from "./errors.js";
import { binaryRates, confusionCounts, ratesFromCounts } from "./metrics.js";
import {
  f1AtK,
  type Judgments,
  mrr,
  precisionAtK,
  recallAtK,
} from "./ranking.js";

interface RankingCase {
  name: string;
  relevant: Judgments;
  ranked: string[];
  k: number;
  expected: {
    precision_at_k: number;
    recall_at_k: number;
    f1_at_k: number;
    reciprocal_rank: number;
  };
}

interface RankingRefusal {
  name: string;
  relevant: Judgments;
  ranked: string[];
  k: number;
  code: string;
}

interface ClassificationCase {
  name: string;
  y_true: number[];
  y_score: number[];
  threshold: number | null;
  expected: {
    true_positives: number;
    false_positives: number;
    true_negatives: number;
    false_negatives: number;
    accuracy: number;
    precision: number;
    recall: number;
    f1: number;
    false_positive_rate: number;
    false_negative_rate: number;
  };
}

interface ClassificationRefusal {
  name: string;
  y_true: number[];
  y_score: number[];
  code: string | null;
}

interface MetricVectors {
  ranking: RankingCase[];
  ranking_refusals: RankingRefusal[];
  classification: ClassificationCase[];
  classification_refusals: ClassificationRefusal[];
}

const vectors: MetricVectors = JSON.parse(
  readFileSync(
    new URL("../../testdata/vectors/metrics.json", import.meta.url),
    "utf8",
  ),
);

/**
 * The tolerance the Python replay uses, written here as the same literal.
 *
 * The two languages reach these numbers by different routes (a C++ trec_eval binary
 * on one side, integer counting on the other), so equality is asserted far tighter
 * than any real disagreement and far looser than double-rounding noise.
 */
const TOLERANCE = 1e-12;

function expectClose(got: number, want: number, label: string): void {
  expect(
    Math.abs(got - want),
    `${label}: got ${got}, want ${want}`,
  ).toBeLessThan(TOLERANCE);
}

/** The vector's null threshold means "call it the way a caller with no opinion would". */
function thresholdOptions(threshold: number | null): { threshold?: number } {
  return threshold === null ? {} : { threshold };
}

function expectCode(call: () => unknown, code: string, label: string): void {
  // The `toThrow` assertion is what guarantees the catch below actually runs; a bare
  // try/catch would pass silently if the call returned a number instead.
  expect(call, label).toThrow(AssayError);
  try {
    call();
  } catch (err) {
    expect((err as AssayError).code, label).toBe(code);
  }
}

describe("ranking vectors replay Python's trec_eval answers", () => {
  it("carries the whole ranking case set", () => {
    expect(vectors.ranking.length).toBeGreaterThanOrEqual(7);
  });

  for (const v of vectors.ranking) {
    it(`vector ${v.name}: every ranking metric matches`, () => {
      const want = v.expected;
      expectClose(
        precisionAtK(v.relevant, v.ranked, v.k),
        want.precision_at_k,
        "P@k",
      );
      expectClose(
        recallAtK(v.relevant, v.ranked, v.k),
        want.recall_at_k,
        "R@k",
      );
      expectClose(f1AtK(v.relevant, v.ranked, v.k), want.f1_at_k, "F1@k");
      expectClose(mrr(v.relevant, v.ranked), want.reciprocal_rank, "RR");
    });
  }
});

describe("ranking refusal vectors refuse with the shared code", () => {
  for (const v of vectors.ranking_refusals) {
    it(`vector ${v.name}: refuses with ${v.code}`, () => {
      expectCode(() => precisionAtK(v.relevant, v.ranked, v.k), v.code, v.name);
    });
  }
});

describe("classification vectors replay Python's scikit-learn answers", () => {
  it("carries the whole classification case set", () => {
    expect(vectors.classification.length).toBeGreaterThanOrEqual(5);
  });

  for (const v of vectors.classification) {
    const options = thresholdOptions(v.threshold);

    it(`vector ${v.name}: the four confusion cells match`, () => {
      // The cells Python's replay re-derives from scikit-learn's recall and accuracy.
      expect(confusionCounts(v.y_true, v.y_score, options)).toEqual({
        truePositives: v.expected.true_positives,
        falsePositives: v.expected.false_positives,
        trueNegatives: v.expected.true_negatives,
        falseNegatives: v.expected.false_negatives,
      });
    });

    it(`vector ${v.name}: every rate matches`, () => {
      const want = v.expected;
      const got = binaryRates(v.y_true, v.y_score, options);
      expectClose(got.accuracy, want.accuracy, "accuracy");
      expectClose(got.precision, want.precision, "precision");
      expectClose(got.recall, want.recall, "recall");
      expectClose(got.f1, want.f1, "f1");
      expectClose(got.falsePositiveRate, want.false_positive_rate, "fpr");
      expectClose(got.falseNegativeRate, want.false_negative_rate, "fnr");
    });

    it(`vector ${v.name}: rates derived from the cells alone agree`, () => {
      // ratesFromCounts is the seam a caller with its own tally uses; it must not be a
      // second opinion.
      expect(
        ratesFromCounts(confusionCounts(v.y_true, v.y_score, options)),
      ).toEqual(binaryRates(v.y_true, v.y_score, options));
    });
  }
});

describe("classification refusal vectors are refused", () => {
  for (const v of vectors.classification_refusals) {
    it(`vector ${v.name}: refuses`, () => {
      const call = () => binaryRates(v.y_true, v.y_score);
      if (v.code === null) {
        // Refused in both languages with different classes: this package raises the
        // coded InvalidScoreRequest, Python lets scikit-learn refuse the multiclass
        // target with an uncoded ValueError. The accept/reject boundary is identical.
        expect(call).toThrow(InvalidScoreRequest);
        return;
      }
      expectCode(call, v.code, v.name);
    });
  }
});
