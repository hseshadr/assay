"""Ranked-retrieval metrics — how good is this ordering, not how good is this score.

``metrics.py`` scores ``(y_true, y_score)`` pairs. That shape cannot express retrieval
quality at all, because it has no notion of *position*: a search engine that returns the
right product tenth and a search engine that returns it first produce the same numbers.
This module scores a ``(relevance judgments, ranked list)`` pair instead, which is what a
search or recommendation system actually emits.

The arithmetic is scikit-learn's — ``ndcg_score`` for the position discount and
``label_ranking_average_precision_score`` for average precision. Assay contributes three
things sklearn does not: the input adaptation from a ranked id list to sklearn's fixed
label matrix, an ``@k`` form for the four set-arithmetic metrics (sklearn ships none),
and a refusal for every input whose answer would be undefined.

One-line definitions, since none of these terms carry themselves:

- **precision@k** — of the top k positions, what fraction held a relevant document.
- **recall@k** — of everything judged relevant, what fraction reached the top k.
- **nDCG@k** — how close this ordering is to the best possible one, with each position
  discounted by ``1/log2(rank + 1)`` so a hit at rank 1 counts more than one at rank 10.
- **MRR** — 1 / (position of the first relevant hit).
- **average precision** — precision measured at every hit position, averaged over the
  whole relevant set; its mean across queries is MAP.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping, Sequence

import numpy as np
from pydantic import BaseModel, ConfigDict
from sklearn.metrics import label_ranking_average_precision_score, ndcg_score

from assay.errors import EmptyRelevantSet, InvalidRankingRequest
from assay.models import RankedQuery
from assay.settings import AssaySettings
from assay.uncertainty import Estimate, mean_interval

type Judgments = Mapping[str, float]
"""Document id -> graded gain. Gain > 0 means relevant; larger means more relevant."""

# Scores handed to sklearn for the positions the ranker did NOT fill, for relevant
# documents it never returned, and for the inert padding column. The three tiers only
# have to be strictly ordered — the values themselves never reach a result.
_FILLER_SCORE = 0.5
_UNRETRIEVED_SCORE = 0.0
_PADDING_SCORE = -1.0

__all__ = [
    "Judgments",
    "QueryRanking",
    "RankingReport",
    "average_precision",
    "binary_judgments",
    "f1_at_k",
    "mean_average_precision",
    "mrr",
    "ndcg_at_k",
    "precision_at_k",
    "ranking_report",
    "recall_at_k",
]


class QueryRanking(BaseModel):
    """Every metric for one query, so a mean can never hide which query failed."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    query: str
    precision_at_k: float
    recall_at_k: float
    f1_at_k: float
    ndcg_at_k: float
    reciprocal_rank: float
    average_precision: float


class RankingReport(BaseModel):
    """A whole query set's metrics: every query, the means, and an interval on nDCG.

    ``ndcg_interval`` is a bootstrap confidence interval over the per-query nDCG@k
    values, or an ``Abstention`` when there are fewer queries than the sample floor. It
    is the same uncertainty story the classification face already tells, not a second
    one: a mean nDCG over eight queries is a number the data cannot support, and saying
    so is more useful than printing it."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    k: int
    n_queries: int
    per_query: tuple[QueryRanking, ...]
    mean_precision_at_k: float
    mean_recall_at_k: float
    mean_f1_at_k: float
    mean_ndcg_at_k: float
    mrr: float
    mean_average_precision: float
    ndcg_interval: Estimate


def binary_judgments(doc_ids: Iterable[str]) -> dict[str, float]:
    """A relevant *set* as judgments: every listed document gets gain 1.0."""
    return dict.fromkeys(doc_ids, 1.0)


def _require_positive_k(k: int) -> None:
    if k <= 0:
        raise InvalidRankingRequest(f"k must be positive, got {k}")


def _require_ranked(ranked: Sequence[str]) -> None:
    if not ranked:
        raise InvalidRankingRequest("ranked list is empty; nothing was returned to score")
    if len(set(ranked)) != len(ranked):
        raise InvalidRankingRequest("ranked list holds the same document id twice")


def _require_judged(relevant: Judgments) -> None:
    if any(gain < 0 for gain in relevant.values()):
        raise InvalidRankingRequest("relevance gains must be non-negative")
    if not any(gain > 0 for gain in relevant.values()):
        raise EmptyRelevantSet("no document is judged relevant for this query")


def _validate(relevant: Judgments, ranked: Sequence[str]) -> None:
    _require_ranked(ranked)
    _require_judged(relevant)


def _n_relevant(relevant: Judgments) -> int:
    return sum(1 for gain in relevant.values() if gain > 0)


def _hits(relevant: Judgments, ranked: Sequence[str]) -> list[bool]:
    return [relevant.get(doc, 0.0) > 0 for doc in ranked]


def precision_at_k(relevant: Judgments, ranked: Sequence[str], k: int) -> float:
    """Fraction of the top ``k`` positions that held a relevant document.

    The denominator is ``k``, not ``min(k, len(ranked))`` — trec_eval's convention. A
    result list shorter than k is a real cost to the user, and dividing by the list
    length would let a ranker score a perfect precision@10 by returning one good hit."""
    _validate(relevant, ranked)
    _require_positive_k(k)
    return sum(_hits(relevant, ranked[:k])) / k


def recall_at_k(relevant: Judgments, ranked: Sequence[str], k: int) -> float:
    """Fraction of ALL judged-relevant documents that reached the top ``k``.

    The denominator is the size of the relevant set and never ``k``. Dividing by ``k``
    is the classic recall bug: it silently reports precision under recall's name, so a
    ranker that misses half the relevant documents still looks complete."""
    _validate(relevant, ranked)
    _require_positive_k(k)
    return sum(_hits(relevant, ranked[:k])) / _n_relevant(relevant)


def f1_at_k(relevant: Judgments, ranked: Sequence[str], k: int) -> float:
    """Harmonic mean of precision@k and recall@k; 0.0 when both are 0."""
    precision = precision_at_k(relevant, ranked, k)
    recall = recall_at_k(relevant, ranked, k)
    if precision + recall == 0:
        return 0.0
    return 2 * precision * recall / (precision + recall)


def _returned_columns(
    relevant: Judgments, ranked: Sequence[str], k: int
) -> tuple[list[float], list[float]]:
    """The k positions the ranker was asked to fill: its list, then zero-gain padding.

    Padding the unfilled positions is what stops a short list borrowing credit at
    positions it never returned anything for."""
    n = len(ranked)
    unfilled = max(0, k - n)
    gains = [relevant.get(doc, 0.0) for doc in ranked] + [0.0] * unfilled
    scores = [float(n - i) for i in range(n)] + [_FILLER_SCORE] * unfilled
    return gains, scores


def _missed_columns(relevant: Judgments, ranked: Sequence[str]) -> tuple[list[float], list[float]]:
    """Relevant documents the ranker never returned, scored below every filled position.

    They can therefore only raise the *ideal* ranking, which is exactly how a miss gets
    charged: retrieving 1 of 4 relevant documents perfectly is not a perfect ranking."""
    returned = set(ranked)
    missed = [gain for doc, gain in relevant.items() if gain > 0 and doc not in returned]
    return missed, [_UNRETRIEVED_SCORE] * len(missed)


def _ndcg_columns(
    relevant: Judgments, ranked: Sequence[str], k: int
) -> tuple[list[float], list[float]]:
    """Adapt (judgments, ranked list) to sklearn's one-row (gains, scores) label matrix.

    sklearn wants a fixed set of labels with a true gain and a predicted score each; a
    ranked id list has neither. The adaptation is positional only — descending scores
    reproduce the given order — so all the DCG arithmetic stays sklearn's. The trailing
    zero-gain column is inert padding: ``ndcg_score`` needs at least two labels, and a
    single-document ranking would otherwise be unscoreable."""
    returned_gains, returned_scores = _returned_columns(relevant, ranked, k)
    missed_gains, missed_scores = _missed_columns(relevant, ranked)
    return (
        [*returned_gains, *missed_gains, 0.0],
        [*returned_scores, *missed_scores, _PADDING_SCORE],
    )


def ndcg_at_k(relevant: Judgments, ranked: Sequence[str], k: int) -> float:
    """Normalized discounted cumulative gain at ``k`` — ``sklearn.metrics.ndcg_score``.

    Supports graded relevance: a gain of 3 at rank 1 outscores a gain of 1 at rank 1.
    The ideal is taken over every judged-relevant document, including ones the ranker
    never returned, so nDCG cannot be maximised by returning less.

    ``ignore_ties=True`` is safe here and makes the result order-deterministic: the only
    tied scores are zero-gain padding and out-of-top-k misses, whose order cannot move
    the number."""
    _validate(relevant, ranked)
    _require_positive_k(k)
    gains, scores = _ndcg_columns(relevant, ranked, k)
    return float(ndcg_score(np.array([gains]), np.array([scores]), k=k, ignore_ties=True))


def mrr(relevant: Judgments, ranked: Sequence[str]) -> float:
    """Reciprocal rank of the first relevant document; 0.0 if the list holds none."""
    _validate(relevant, ranked)
    for position, hit in enumerate(_hits(relevant, ranked), start=1):
        if hit:
            return 1.0 / position
    return 0.0


def average_precision(relevant: Judgments, ranked: Sequence[str]) -> float:
    """Average precision over the whole ranked list — sklearn's LRAP, rescaled.

    ``label_ranking_average_precision_score`` averages precision over the relevant labels
    *it is given*. Run over the returned list it therefore divides by the number of
    relevant documents RETRIEVED, while classical average precision divides by the number
    judged relevant overall. The two differ by exactly that ratio, so it is applied here
    at the boundary — retrieving 3 of 30 relevant documents flawlessly is AP 0.1, not AP
    1.0. Every per-position precision term stays sklearn's.

    The trailing zero column is the same inert padding ``ndcg_at_k`` uses; it also keeps
    sklearn off its "all labels relevant" shortcut, which returns 1.0 without measuring."""
    _validate(relevant, ranked)
    labels = [1 if relevant.get(doc, 0.0) > 0 else 0 for doc in ranked]
    scores = [float(len(ranked) - i) for i in range(len(ranked))]
    lrap = float(
        label_ranking_average_precision_score(
            np.array([[*labels, 0]]), np.array([[*scores, _PADDING_SCORE]])
        )
    )
    return lrap * sum(labels) / _n_relevant(relevant)


def _gains(query: RankedQuery) -> dict[str, float]:
    """A query's judgments as a doc-id map, refusing a document judged twice."""
    gains = {judgment.doc_id: judgment.gain for judgment in query.judgments}
    if len(gains) != len(query.judgments):
        raise InvalidRankingRequest(f"query {query.query!r} judges a document twice")
    return gains


def _require_queries(queries: Sequence[RankedQuery]) -> None:
    if not queries:
        raise InvalidRankingRequest("query set is empty; there is nothing to average over")


def mean_average_precision(queries: Sequence[RankedQuery]) -> float:
    """MAP: the mean of every query's average precision."""
    _require_queries(queries)
    return float(np.mean([average_precision(_gains(q), q.ranked) for q in queries]))


def _mean_of(rows: Sequence[QueryRanking], pick: Callable[[QueryRanking], float]) -> float:
    return float(np.mean([pick(row) for row in rows]))


def _query_ranking(query: RankedQuery, k: int) -> QueryRanking:
    gains = _gains(query)
    return QueryRanking(
        query=query.query,
        precision_at_k=precision_at_k(gains, query.ranked, k),
        recall_at_k=recall_at_k(gains, query.ranked, k),
        f1_at_k=f1_at_k(gains, query.ranked, k),
        ndcg_at_k=ndcg_at_k(gains, query.ranked, k),
        reciprocal_rank=mrr(gains, query.ranked),
        average_precision=average_precision(gains, query.ranked),
    )


def _ndcg_interval(rows: tuple[QueryRanking, ...], settings: AssaySettings) -> Estimate:
    return mean_interval(
        [row.ndcg_at_k for row in rows],
        min_samples=settings.min_samples,
        n_resamples=settings.bootstrap_resamples,
        confidence_level=settings.confidence_level,
        seed=settings.bootstrap_seed,
    )


def _report(rows: tuple[QueryRanking, ...], k: int, settings: AssaySettings) -> RankingReport:
    return RankingReport(
        k=k,
        n_queries=len(rows),
        per_query=rows,
        mean_precision_at_k=_mean_of(rows, lambda row: row.precision_at_k),
        mean_recall_at_k=_mean_of(rows, lambda row: row.recall_at_k),
        mean_f1_at_k=_mean_of(rows, lambda row: row.f1_at_k),
        mean_ndcg_at_k=_mean_of(rows, lambda row: row.ndcg_at_k),
        mrr=_mean_of(rows, lambda row: row.reciprocal_rank),
        mean_average_precision=_mean_of(rows, lambda row: row.average_precision),
        ndcg_interval=_ndcg_interval(rows, settings),
    )


def ranking_report(
    queries: Sequence[RankedQuery], *, settings: AssaySettings, k: int | None = None
) -> RankingReport:
    """Score a whole query set: every query's metrics, their means, and an interval.

    ``k`` defaults to ``settings.ranking_k`` — nothing here is hardcoded. The per-query
    rows are returned in full alongside the means, because the mean is the number that
    hides a broken query and the rows are the number that names it."""
    resolved_k = settings.ranking_k if k is None else k
    _require_positive_k(resolved_k)
    _require_queries(queries)
    rows = tuple(_query_ranking(query, resolved_k) for query in queries)
    return _report(rows, resolved_k, settings)
