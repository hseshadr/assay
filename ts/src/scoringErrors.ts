/**
 * Coded scoring-error catalog — the TypeScript mirror of Python `assay.errors`.
 *
 * These are deliberately a separate family from the `avow.*` envelope errors in
 * `errors.ts`, exactly as Python keeps `assay.errors` apart from `avow.errors`.
 * The envelope answers "is this receipt genuine"; these answer "can this input be
 * scored at all". A caller that catches one should never accidentally swallow the
 * other.
 *
 * Every code below is byte-identical to the string the Python face raises, so a
 * browser and a server refusing the same input report the same `code`.
 */

/** Base class for every Assay scoring-face error. */
export class AssayError extends Error {
  public readonly code: string = "assay.error";

  public constructor(message: string, options?: ErrorOptions) {
    super(message, options);
    this.name = new.target.name;
  }
}

/**
 * Inputs are malformed: length mismatch, empty, single-class, or a label that is
 * not 0 or 1.
 *
 * Mirrors Python `assay.errors.InvalidScoreRequest` (`assay.invalid_request`).
 */
export class InvalidScoreRequest extends AssayError {
  public override readonly code = "assay.invalid_request";
}

/**
 * A ranked-retrieval input cannot be scored as given.
 *
 * Covers `k <= 0` and a non-integer `k`, an empty ranked list, the same document
 * twice in one ranked list, and a negative or fractional relevance gain. Each of
 * these makes some metric's answer undefined rather than merely small, so the face
 * refuses instead of returning a number whose meaning nobody could state.
 *
 * Mirrors Python `assay.errors.InvalidRankingRequest`.
 */
export class InvalidRankingRequest extends AssayError {
  public override readonly code = "assay.invalid_ranking_request";
}

/**
 * No document is judged relevant, so recall has no denominator.
 *
 * Returning 0.0 here would read as "the ranker found nothing" and blame the ranker
 * for missing *judgments*. Those are different failures with different fixes, so
 * they get different answers: a real 0.0 when the ranker misses, a refusal when
 * nobody judged.
 *
 * Mirrors Python `assay.errors.EmptyRelevantSet`.
 */
export class EmptyRelevantSet extends AssayError {
  public override readonly code = "assay.empty_relevant_set";
}
