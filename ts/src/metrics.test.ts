/**
 * The binary-classification face, pinned to hand-computed worked examples.
 *
 * Every expected number was computed by hand from the metric's definition (the
 * `// hand:` comments show the arithmetic), never read back out of the code under
 * test. The same numbers are asserted against Python's scikit-learn answers by the
 * shared vectors in `metricVectors.test.ts` / `tests/test_metric_vectors.py`.
 */

import { describe, expect, it } from "vitest";
import { AssayError, InvalidScoreRequest } from "./errors.js";
import {
  binaryRates,
  confusionCounts,
  DEFAULT_THRESHOLD,
  ratesFromCounts,
} from "./metrics.js";

// Predictions at 0.5 are (0,1,0,1) against labels (0,0,1,1): one of every cell.
const Y_TRUE = [0, 0, 1, 1];
const Y_SCORE = [0.1, 0.9, 0.2, 0.8];

describe("confusion cells", () => {
  it("counts one of every cell and names each one", () => {
    // Given one true negative, one false alarm, one miss and one hit
    // When the cells are counted at 0.5
    // Then each lands in the cell its own name describes
    expect(confusionCounts(Y_TRUE, Y_SCORE)).toEqual({
      trueNegatives: 1, // hand: label 0, score 0.1 -> predicted 0
      falsePositives: 1, // hand: label 0, score 0.9 -> predicted 1
      falseNegatives: 1, // hand: label 1, score 0.2 -> predicted 0
      truePositives: 1, // hand: label 1, score 0.8 -> predicted 1
    });
  });

  it("treats a score exactly equal to the threshold as positive", () => {
    // Given two scores sitting exactly on the threshold
    // When the cells are counted
    // Then both are POSITIVE predictions — the comparison is >=, as in Python.
    // Under `>` both would flip to negative and all four cells would change.
    expect(confusionCounts([0, 1], [0.5, 0.5], { threshold: 0.5 })).toEqual({
      truePositives: 1,
      falsePositives: 1,
      trueNegatives: 0,
      falseNegatives: 0,
    });
  });

  it("moves the cells when the threshold moves", () => {
    // Given the same scores read at 0.85, where only 0.9 clears the bar
    // When the cells are counted
    // Then predictions are (0,1,0,0): no hits, one false alarm, two misses
    expect(confusionCounts(Y_TRUE, Y_SCORE, { threshold: 0.85 })).toEqual({
      truePositives: 0,
      falsePositives: 1,
      trueNegatives: 1,
      falseNegatives: 2,
    });
  });

  it("uses the documented default threshold of 0.5", () => {
    // Given a caller with no opinion about the threshold
    // When the cells are counted with and without an explicit 0.5
    // Then the answers are identical, and the default is the literal 0.5 the docs
    // state out loud — asserted against the number, not against itself
    expect(DEFAULT_THRESHOLD).toBe(0.5);
    expect(confusionCounts(Y_TRUE, Y_SCORE)).toEqual(
      confusionCounts(Y_TRUE, Y_SCORE, { threshold: 0.5 }),
    );
  });
});

describe("rates", () => {
  it("computes each rate from its own two cells", () => {
    // Given tp=1, fp=1, tn=1, fn=1
    // When the rates are taken
    // Then each is the textbook ratio
    const rates = binaryRates(Y_TRUE, Y_SCORE);
    expect(rates.accuracy).toBe(0.5); // hand: (1+1)/4
    expect(rates.precision).toBe(0.5); // hand: 1/(1+1)
    expect(rates.recall).toBe(0.5); // hand: 1/(1+1)
    expect(rates.f1).toBe(0.5); // hand: 2*.5*.5/(.5+.5)
    expect(rates.falsePositiveRate).toBe(0.5); // hand: 1/(1+1)
    expect(rates.falseNegativeRate).toBe(0.5); // hand: 1/(1+1)
  });

  it("keeps the false-positive rate distinct from the false-negative rate", () => {
    // Given an imbalanced screen: 8 negatives, 2 positives, 2 false alarms, 1 miss
    const yTrue = [0, 0, 0, 0, 0, 0, 0, 0, 1, 1];
    const yScore = [0.1, 0.2, 0.3, 0.4, 0.55, 0.6, 0.05, 0.15, 0.45, 0.95];
    // When both error rates are taken
    // Then they are different numbers over different denominators. Computing one as
    // the other is the classic silent inversion: it swaps a miss for a false alarm
    // while accuracy, precision and recall all stay put.
    const rates = binaryRates(yTrue, yScore);
    expect(rates.falsePositiveRate).toBe(0.25); // hand: fp 2 / (fp 2 + tn 6)
    expect(rates.falseNegativeRate).toBe(0.5); // hand: fn 1 / (fn 1 + tp 1)
    expect(rates.accuracy).toBe(0.7); // hand: (1+6)/10 — high while half is missed
    expect(rates.precision).toBeCloseTo(1 / 3, 15); // hand: 1/(1+2)
  });

  it("reports the false-negative rate as the miss rate, one minus recall", () => {
    // Given a threshold so high that every positive is missed
    // When the rates are taken
    // Then FNR is 1.0, and it is 1 - recall rather than recall itself
    const rates = binaryRates(Y_TRUE, Y_SCORE, { threshold: 0.85 });
    expect(rates.recall).toBe(0); // hand: 0/(0+2)
    expect(rates.falseNegativeRate).toBe(1); // hand: 2/(2+0)
  });

  it("reports zero, not NaN, when nothing was predicted positive", () => {
    // Given a threshold above every score, so tp + fp is 0
    // When precision and F1 are taken
    // Then both are 0 — scikit-learn's zero_division=0.0, which is what Python
    // passes. A NaN here would poison every average computed downstream.
    const rates = binaryRates(Y_TRUE, Y_SCORE, { threshold: 1.5 });
    expect(rates.precision).toBe(0); // hand: 0/0 -> 0
    expect(rates.f1).toBe(0); // hand: 0/0 -> 0
    expect(rates.recall).toBe(0);
    expect(rates.falsePositiveRate).toBe(0); // hand: 0/(0+2)
  });

  it("scores perfect separation as one across the board", () => {
    // Given a threshold that splits the labels exactly
    // When the rates are taken
    // Then every rate is at its best value, and both error rates are 0
    expect(binaryRates([0, 0, 1, 1], [0.1, 0.2, 0.8, 0.9])).toEqual({
      accuracy: 1,
      precision: 1,
      recall: 1,
      f1: 1,
      falsePositiveRate: 0,
      falseNegativeRate: 0,
    });
  });
});

describe("ratesFromCounts", () => {
  it("derives the same rates from cells a caller tallied itself", () => {
    // Given cells counted by the caller rather than by this package
    // When the rates are derived
    // Then they match the ones taken straight from labels and scores, so the seam
    // for a caller with its own tally is not a second opinion
    expect(
      ratesFromCounts({
        truePositives: 1,
        falsePositives: 1,
        trueNegatives: 1,
        falseNegatives: 1,
      }),
    ).toEqual(binaryRates(Y_TRUE, Y_SCORE));
  });

  it("reports zeroes rather than NaN for an all-zero tally", () => {
    // Given a tally with nothing in it at all
    // When the rates are derived
    // Then every rate is 0 — this is the only entry point that can reach a zero
    // total, because the scored entry points refuse an empty input first
    expect(
      ratesFromCounts({
        truePositives: 0,
        falsePositives: 0,
        trueNegatives: 0,
        falseNegatives: 0,
      }),
    ).toEqual({
      accuracy: 0,
      precision: 0,
      recall: 0,
      f1: 0,
      falsePositiveRate: 0,
      falseNegativeRate: 0,
    });
  });
});

describe("refusals", () => {
  function expectCode(call: () => unknown, code: string): void {
    expect(call).toThrow(AssayError);
    try {
      call();
    } catch (err) {
      expect((err as AssayError).code).toBe(code);
    }
  }

  it("refuses a length mismatch", () => {
    // Given more labels than scores
    // When scored
    // Then it refuses — there is no pairing to score
    expectCode(() => binaryRates([0, 1], [0.5]), "assay.invalid_request");
    expect(() => confusionCounts([0, 1], [0.5])).toThrow(InvalidScoreRequest);
  });

  it("refuses empty inputs", () => {
    // Given nothing to score
    // When scored
    // Then it refuses rather than dividing every rate by zero
    expectCode(() => binaryRates([], []), "assay.invalid_request");
  });

  it("refuses a single-class label set", () => {
    // Given labels that are all 1
    // When scored
    // Then it refuses, matching Python — an input that scores in the browser and
    // refuses on the server is the divergence the shared contract exists to stop
    expectCode(
      () => binaryRates([1, 1, 1], [0.2, 0.8, 0.5]),
      "assay.invalid_request",
    );
  });

  it("refuses a label that is not 0 or 1", () => {
    // Given a multiclass target
    // When scored
    // Then it refuses. Python has no check of its own here and lets scikit-learn
    // refuse with an uncoded ValueError; there is no scikit-learn in a browser, so
    // the same input is refused explicitly and the boundary stays identical.
    expectCode(
      () => binaryRates([0, 1, 2], [0.1, 0.6, 0.9]),
      "assay.invalid_request",
    );
    expect(() => binaryRates([0, -1], [0.1, 0.6])).toThrow(InvalidScoreRequest);
  });
});
