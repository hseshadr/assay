/**
 * Ranked-retrieval metrics for the browser — the TypeScript face of Python
 * `assay.ranking`.
 *
 * `metrics.ts` scores `(yTrue, yScore)` pairs. That shape cannot express retrieval
 * quality at all, because it has no notion of *position*: a search engine that
 * returns the right product tenth and one that returns it first produce the same
 * numbers. This module scores a `(relevance judgments, ranked list)` pair instead,
 * which is what a search or recommendation system actually emits.
 *
 * One-line definitions, since none of these terms carry themselves:
 *
 * - **precision@k** — of the top k positions, what fraction held a relevant document.
 * - **recall@k** — of everything judged relevant, what fraction reached the top k.
 * - **F1@k** — the harmonic mean of the two.
 * - **MRR** — 1 / (position of the first relevant hit).
 *
 * *Why this is written out rather than wrapped.* Python reaches `trec_eval`'s
 * arithmetic through `ir_measures`, whose engine is a C++ binary — there is no
 * npm binding, and none of the JavaScript alternatives clears the bar: the closest
 * candidates are `ml-confusion-matrix` (mljs, last published 2023-01, and a matrix
 * container rather than a metric reference), `node-dcg` (one maintainer, 2023) and
 * a handful of 0.1.0 single-author packages published this year. None is the
 * reference implementation its field validates against, so wrapping one would buy
 * a dependency and no correctness. These three metrics are instead written against
 * their definitions — which is safe *only* because every number here is pinned to
 * Python's `trec_eval` answer by the shared golden vectors in
 * `testdata/vectors/metrics.json`, replayed by both suites. Divergence fails CI in
 * both languages.
 *
 * Deliberately absent, and staying absent: **nDCG@k** and **average precision /
 * MAP**. Both are `trec_eval`'s, and both carry conventions (the idealisation over
 * unretrieved judgments, the graded-to-binary collapse, truncation behaviour) that
 * belong to that implementation rather than to any textbook. Approximating them
 * here would produce a number that looks like Python's and is not. Python remains
 * their only implementation.
 */

import { EmptyRelevantSet, InvalidRankingRequest } from "./errors.js";

/**
 * Document id -> graded gain. Gain > 0 means relevant; larger means more relevant.
 *
 * A judged document with gain 0 is judged *not* relevant — it counts towards
 * neither the hits nor the recall denominator.
 */
export type Judgments = Readonly<Record<string, number>>;

/**
 * A relevant *set* as judgments: every listed document gets gain 1.
 *
 * The accumulator has a **null prototype**, and that is load-bearing rather than
 * defensive habit. `plain["__proto__"] = 1` does not create a property — it invokes
 * `Object.prototype`'s `__proto__` setter, which ignores a non-object value — so a
 * document literally called `__proto__` silently vanished from the judgments. Python
 * has no such rule, and `binary_judgments(["__proto__"])` keeps it. That made
 * precision@1 over a `__proto__` document **1.0 in Python and 0 in the browser**: not
 * a refusal, not a rounding difference, just two languages confidently printing
 * different numbers. Pinned by the `document_id_named_proto` shared vector.
 */
export function binaryJudgments(docIds: Iterable<string>): Judgments {
  const judgments: Record<string, number> = Object.create(null);
  for (const docId of docIds) {
    judgments[docId] = 1;
  }
  return judgments;
}

/**
 * `k` must be a positive whole number.
 *
 * Python declares `k: int` and mypy `--strict` enforces that at the call site.
 * TypeScript's `number` cannot, so the same contract is checked at run time here —
 * `precisionAtK(j, r, 2.5)` is a request nobody can state the meaning of.
 */
function requirePositiveK(k: number): void {
  if (!Number.isInteger(k)) {
    throw new InvalidRankingRequest(`k must be a whole number, got ${k}`);
  }
  if (k <= 0) {
    throw new InvalidRankingRequest(`k must be positive, got ${k}`);
  }
}

function requireRanked(ranked: readonly string[]): void {
  if (ranked.length === 0) {
    throw new InvalidRankingRequest(
      "ranked list is empty; nothing was returned to score",
    );
  }
  if (new Set(ranked).size !== ranked.length) {
    throw new InvalidRankingRequest(
      "ranked list holds the same document id twice",
    );
  }
}

/**
 * Gains must be non-negative whole numbers — a relevance grade is a level, not a
 * quantity, and trec_eval qrels are integer-graded by definition.
 *
 * A fractional gain is refused rather than rounded. Rounding 0.5 down would move
 * that document from relevant to irrelevant and quietly change the answer, and
 * there is no reference semantics saying which way it should go.
 */
function requireGraded(relevant: Judgments): void {
  for (const [doc, gain] of Object.entries(relevant)) {
    if (gain < 0) {
      throw new InvalidRankingRequest("relevance gains must be non-negative");
    }
    if (!Number.isInteger(gain)) {
      throw new InvalidRankingRequest(
        `relevance gain for '${doc}' is not whole: ${gain}`,
      );
    }
  }
}

function relevantCount(relevant: Judgments): number {
  return Object.values(relevant).filter((gain) => gain > 0).length;
}

function requireRelevant(relevant: Judgments): void {
  if (relevantCount(relevant) === 0) {
    throw new EmptyRelevantSet("no document is judged relevant for this query");
  }
}

function validate(relevant: Judgments, ranked: readonly string[]): void {
  requireRanked(ranked);
  requireGraded(relevant);
  requireRelevant(relevant);
}

function validateAtK(
  relevant: Judgments,
  ranked: readonly string[],
  k: number,
): void {
  validate(relevant, ranked);
  requirePositiveK(k);
}

/**
 * `Object.hasOwn`, not a bare index read: `relevant['constructor']` on a plain
 * object literal resolves up the prototype chain and hands back a function. Only
 * an own key is a judgment.
 */
function isRelevant(relevant: Judgments, doc: string): boolean {
  return Object.hasOwn(relevant, doc) && (relevant[doc] as number) > 0;
}

function hitsInTopK(
  relevant: Judgments,
  ranked: readonly string[],
  k: number,
): number {
  return ranked.slice(0, k).filter((doc) => isRelevant(relevant, doc)).length;
}

/**
 * Fraction of the top `k` positions that held a relevant document.
 *
 * The denominator is `k`, not `min(k, ranked.length)` — trec_eval's convention. A
 * result list shorter than k is a real cost to the user, and dividing by the list
 * length would let a ranker score a perfect precision@10 by returning one good hit.
 */
export function precisionAtK(
  relevant: Judgments,
  ranked: readonly string[],
  k: number,
): number {
  validateAtK(relevant, ranked, k);
  return hitsInTopK(relevant, ranked, k) / k;
}

/**
 * Fraction of ALL judged-relevant documents that reached the top `k`.
 *
 * The denominator is the size of the relevant set and never `k`. Dividing by `k`
 * is the classic recall bug: it silently reports precision under recall's name, so
 * a ranker that misses half the relevant documents still looks complete.
 */
export function recallAtK(
  relevant: Judgments,
  ranked: readonly string[],
  k: number,
): number {
  validateAtK(relevant, ranked, k);
  return hitsInTopK(relevant, ranked, k) / relevantCount(relevant);
}

/** Harmonic mean of precision@k and recall@k; 0 when both are 0. */
export function f1AtK(
  relevant: Judgments,
  ranked: readonly string[],
  k: number,
): number {
  const precision = precisionAtK(relevant, ranked, k);
  const recall = recallAtK(relevant, ranked, k);
  if (precision + recall === 0) {
    return 0;
  }
  return (2 * precision * recall) / (precision + recall);
}

/**
 * Reciprocal rank of the first relevant document; 0 if the list holds none.
 *
 * Untruncated, matching trec_eval's `recip_rank`: a hit at position 40 scores
 * 1/40, not 0.
 */
export function mrr(relevant: Judgments, ranked: readonly string[]): number {
  validate(relevant, ranked);
  const position = ranked.findIndex((doc) => isRelevant(relevant, doc));
  return position === -1 ? 0 : 1 / (position + 1);
}
