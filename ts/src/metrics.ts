/**
 * Binary-classification metrics for the browser — the TypeScript face of Python
 * `assay.metrics`.
 *
 * Scores `(yTrue, yScore)` pairs at a decision threshold: the four confusion cells
 * and the rates they determine. Python reaches these through scikit-learn; there
 * is no scikit-learn in a browser and no npm package that is the reference
 * implementation of anything here (see `ranking.ts` for that audit), so the cells
 * are counted directly and every rate is the textbook ratio of two of them. Both
 * are safe to write out *only* because they are pinned to Python's scikit-learn
 * answers by the shared golden vectors in `testdata/vectors/metrics.json`, which
 * both suites replay.
 *
 * **What this deliberately does not ship: PR-AUC and ROC-AUC.** Python's
 * `binary_scores` returns them, and they are the two metrics on that dataclass
 * that are *not* a ratio of confusion cells — they integrate over every threshold,
 * with scikit-learn's own tie-handling and interpolation conventions. Reproducing
 * those conventions from a definition is exactly the approximation that makes two
 * languages print different numbers for the same input. Python remains their only
 * implementation.
 *
 * **The two-class floor is kept anyway.** It exists in Python because the AUCs are
 * undefined on one class, and this module has no AUCs — but dropping it would mean
 * an input that scores in the browser and refuses on the server, which is the one
 * failure the cross-language contract exists to prevent. It also earns its keep:
 * with both classes present, the actual-positive and actual-negative counts are
 * both at least one, so recall, FPR and FNR can never divide by zero.
 */

import { InvalidScoreRequest } from "./scoringErrors.js";

/**
 * The default decision threshold, matching Python's `binary_scores(threshold=0.5)`.
 *
 * A score exactly equal to the threshold is a POSITIVE prediction — the comparison
 * is `>=`, as it is in Python.
 */
export const DEFAULT_THRESHOLD = 0.5;

/**
 * The four cells of a binary confusion matrix at one threshold.
 *
 * Named cells, not a bare 2x2 array. scikit-learn's `confusion_matrix(...).ravel()`
 * returns them in the order `tn, fp, fn, tp`, and reading that tuple in the wrong
 * order is the classic silent inversion: it swaps a miss for a false alarm while
 * every total still adds up, so nothing downstream can notice.
 */
export interface ConfusionCounts {
  readonly truePositives: number;
  readonly falsePositives: number;
  readonly trueNegatives: number;
  readonly falseNegatives: number;
}

/**
 * The rates the four cells determine.
 *
 * `falseNegativeRate` is named rather than left as `1 - recall`, because a miss
 * rate is the number a screening system is actually judged on and the subtraction
 * is where the sign gets flipped.
 */
export interface BinaryRates {
  readonly accuracy: number;
  readonly precision: number;
  readonly recall: number;
  readonly f1: number;
  readonly falsePositiveRate: number;
  readonly falseNegativeRate: number;
}

/** Options for the thresholded metrics. */
export interface ThresholdOptions {
  readonly threshold?: number;
}

const POSITIVE = 1;
const NEGATIVE = 0;
const MIN_CLASSES = 2;

function requireBinaryLabels(yTrue: readonly number[]): void {
  for (const label of yTrue) {
    if (label !== POSITIVE && label !== NEGATIVE) {
      throw new InvalidScoreRequest(
        `y_true holds ${label}; binary labels must be 0 or 1`,
      );
    }
  }
}

/**
 * Mirrors Python `assay.metrics._validate`, plus the 0/1 label check.
 *
 * Python does not check labels itself — it lets scikit-learn refuse a multiclass
 * target with a `ValueError`. There is no scikit-learn here to refuse on this
 * module's behalf, so the same input is refused explicitly. The accept/reject
 * boundary is therefore identical in both languages; only the class of the thrown
 * error differs, and the golden vector records that row as "refused in both"
 * rather than pinning a shared code it does not have.
 */
function validate(yTrue: readonly number[], yScore: readonly number[]): void {
  if (yTrue.length !== yScore.length) {
    throw new InvalidScoreRequest("y_true and y_score length mismatch");
  }
  if (yTrue.length === 0) {
    throw new InvalidScoreRequest("inputs are empty");
  }
  requireBinaryLabels(yTrue);
  if (new Set(yTrue).size < MIN_CLASSES) {
    throw new InvalidScoreRequest("need both classes present for AUC metrics");
  }
}

/** Count the four cells at `threshold`. Validation is the caller's job. */
function tally(
  yTrue: readonly number[],
  yScore: readonly number[],
  threshold: number,
): ConfusionCounts {
  let truePositives = 0;
  let falsePositives = 0;
  let trueNegatives = 0;
  let falseNegatives = 0;
  for (const [index, actual] of yTrue.entries()) {
    const predictedPositive = (yScore[index] as number) >= threshold;
    if (actual === POSITIVE && predictedPositive) {
      truePositives += 1;
    } else if (actual === POSITIVE) {
      falseNegatives += 1;
    } else if (predictedPositive) {
      falsePositives += 1;
    } else {
      trueNegatives += 1;
    }
  }
  return { truePositives, falsePositives, trueNegatives, falseNegatives };
}

/**
 * The four confusion cells for `(yTrue, yScore)` at a decision threshold.
 *
 * Refuses exactly what Python's `binary_scores` refuses: a length mismatch, an
 * empty input, and a `yTrue` that does not hold both classes.
 */
export function confusionCounts(
  yTrue: readonly number[],
  yScore: readonly number[],
  options: ThresholdOptions = {},
): ConfusionCounts {
  validate(yTrue, yScore);
  return tally(yTrue, yScore, options.threshold ?? DEFAULT_THRESHOLD);
}

/**
 * `numerator / denominator`, or 0 when the denominator is 0.
 *
 * scikit-learn's `zero_division=0.0`, which is what Python's `_prf` passes: a
 * classifier that predicted no positives at all has undefined precision, and
 * assay's Python face reports 0 for it rather than NaN.
 */
function ratio(numerator: number, denominator: number): number {
  return denominator === 0 ? 0 : numerator / denominator;
}

/**
 * Turn counted cells into the rates they determine.
 *
 * Exported separately from `binaryRates` because a caller that already tallied its
 * own outcomes — a screening run that recorded hits and misses as it went — should
 * not have to rebuild two parallel arrays just to divide six pairs of integers.
 */
export function ratesFromCounts(counts: ConfusionCounts): BinaryRates {
  const { truePositives, falsePositives, trueNegatives, falseNegatives } =
    counts;
  const total = truePositives + falsePositives + trueNegatives + falseNegatives;
  const precision = ratio(truePositives, truePositives + falsePositives);
  const recall = ratio(truePositives, truePositives + falseNegatives);
  return {
    accuracy: ratio(truePositives + trueNegatives, total),
    precision,
    recall,
    f1: ratio(2 * precision * recall, precision + recall),
    falsePositiveRate: ratio(falsePositives, falsePositives + trueNegatives),
    falseNegativeRate: ratio(falseNegatives, falseNegatives + truePositives),
  };
}

/**
 * Accuracy, precision, recall, F1, FPR and FNR at a decision threshold.
 *
 * The threshold metrics of Python's `binary_scores`, minus its two AUCs, plus the
 * two rates the confusion cells make free.
 */
export function binaryRates(
  yTrue: readonly number[],
  yScore: readonly number[],
  options: ThresholdOptions = {},
): BinaryRates {
  return ratesFromCounts(confusionCounts(yTrue, yScore, options));
}
