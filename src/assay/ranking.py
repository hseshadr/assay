"""Ranked-retrieval metrics — how good is this ordering, not how good is this score.

``metrics.py`` scores ``(y_true, y_score)`` pairs. That shape cannot express retrieval
quality at all, because it has no notion of *position*: a search engine that returns the
right product tenth and a search engine that returns it first produce the same numbers.
This module scores a ``(relevance judgments, ranked list)`` pair instead, which is what a
search or recommendation system actually emits.

The arithmetic is ``trec_eval``'s, reached through ``ir_measures``. trec_eval is the
reference implementation the IR field validates its own numbers against, so every metric
here is the field's definition rather than assay's reading of it. Assay contributes two
things it does not: a Python-native ``(judgments, ranked list)`` contract in place of
trec_eval's qrels/run file pair, and a refusal for every input whose answer would be
undefined.

*Why not scikit-learn.* ``ndcg_score`` and ``label_ranking_average_precision_score`` are
multilabel-**classification** metrics. Neither has a notion of a relevant document that
was never retrieved, so both had to be talked into retrieval semantics at the boundary:
nDCG by padding the positions the ranker left empty and parking missed documents below
every filled one, average precision by rescaling LRAP by
``|relevant retrieved| / |relevant|`` to undo its habit of dividing by the labels it was
handed — without which, retrieving 1 of 4 relevant documents scored 1.0. Those were
hand-written semantic corrections wrapped around a mismatched engine, and a subtle error
in either would have silently corrupted every number downstream. Both are gone; trec_eval
has these semantics natively.

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

import math
from collections.abc import Callable, Iterable, Mapping, Sequence
from statistics import fmean
from typing import TYPE_CHECKING

from pydantic import BaseModel, ConfigDict

from assay.errors import EmptyRelevantSet, InvalidRankingRequest
from assay.metrics import require_metrics_extra
from assay.models import RankedQuery
from assay.uncertainty import Estimate, mean_interval

if TYPE_CHECKING:
    from ir_measures import AP, RR, Measure, P, R, calc_aggregate, nDCG

    from assay.settings import AssaySettings
else:
    try:
        from ir_measures import AP, RR, Measure, P, R, calc_aggregate, nDCG
    except ImportError:
        AP = None
        RR = None
        Measure = object
        P = None
        R = None
        calc_aggregate = None
        nDCG = None

type Judgments = Mapping[str, float]
"""Document id -> graded gain. Gain > 0 means relevant; larger means more relevant."""

_QUERY = "q"
"""The query id every evaluation runs under. Assay's contract is one query at a time; the
id is an internal join key between the qrels and the run and never reaches a result."""

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
        raise InvalidRankingRequest


def _require_ranked(ranked: Sequence[str]) -> None:
    if not ranked:
        raise InvalidRankingRequest("ranked list is empty; nothing was returned to score")
    if len(set(ranked)) != len(ranked):
        raise InvalidRankingRequest("ranked list holds the same document id twice")


def _require_graded(relevant: Judgments) -> None:
    """Gains must be non-negative whole numbers — a relevance grade is a level, not a
    quantity, and trec_eval qrels are integer-graded by definition.

    A fractional gain is refused rather than rounded. Rounding 0.5 down would move that
    document from relevant to irrelevant and quietly change the answer, and there is no
    reference semantics saying which way it should go."""
    for gain in relevant.values():
        if not math.isfinite(gain) or gain < 0 or gain != int(gain):
            raise InvalidRankingRequest


def _require_relevant(relevant: Judgments) -> None:
    if not any(gain > 0 for gain in relevant.values()):
        raise EmptyRelevantSet("no document is judged relevant for this query")


def _validate(relevant: Judgments, ranked: Sequence[str]) -> None:
    _require_ranked(ranked)
    _require_graded(relevant)
    _require_relevant(relevant)


def _validate_at_k(relevant: Judgments, ranked: Sequence[str], k: int) -> None:
    _validate(relevant, ranked)
    _require_positive_k(k)


def _qrels(relevant: Judgments) -> dict[str, dict[str, int]]:
    """Judgments as trec_eval qrels: one query, one integer grade per judged document.

    Documents the ranker never returned stay in here, which is the whole point — the
    qrels ARE the ideal ranking, so a miss is charged without assay arranging anything."""
    return {_QUERY: {doc: int(gain) for doc, gain in relevant.items()}}


def _run(ranked: Sequence[str]) -> dict[str, dict[str, float]]:
    """The ranked list as a trec_eval run.

    trec_eval orders by score; assay's contract is an already-ordered list. Strictly
    descending scores reproduce the given order exactly, and no two are equal, so no
    tie-breaking rule can move a number."""
    return {_QUERY: {doc: float(len(ranked) - i) for i, doc in enumerate(ranked)}}


def _score(relevant: Judgments, ranked: Sequence[str], measure: Measure) -> float:
    """One trec_eval evaluation of one query. Validation is the caller's job."""
    require_metrics_extra()
    return float(calc_aggregate([measure], _qrels(relevant), _run(ranked))[measure])


def precision_at_k(relevant: Judgments, ranked: Sequence[str], k: int) -> float:
    """Fraction of the top ``k`` positions that held a relevant document.

    The denominator is ``k``, not ``min(k, len(ranked))`` — trec_eval's convention, and
    now trec_eval's own arithmetic. A result list shorter than k is a real cost to the
    user, and dividing by the list length would let a ranker score a perfect
    precision@10 by returning one good hit."""
    require_metrics_extra()
    _validate_at_k(relevant, ranked, k)
    return _score(relevant, ranked, P @ k)


def recall_at_k(relevant: Judgments, ranked: Sequence[str], k: int) -> float:
    """Fraction of ALL judged-relevant documents that reached the top ``k``.

    The denominator is the size of the relevant set and never ``k``. Dividing by ``k``
    is the classic recall bug: it silently reports precision under recall's name, so a
    ranker that misses half the relevant documents still looks complete."""
    require_metrics_extra()
    _validate_at_k(relevant, ranked, k)
    return _score(relevant, ranked, R @ k)


def f1_at_k(relevant: Judgments, ranked: Sequence[str], k: int) -> float:
    """Harmonic mean of precision@k and recall@k; 0.0 when both are 0.

    Composed here rather than delegated: neither ir_measures nor ranx ships an F@k
    (ir_measures has ``SetF`` over the whole run, which is a different number), and the
    harmonic mean of two engine results is composition, not a reimplementation."""
    precision = precision_at_k(relevant, ranked, k)
    recall = recall_at_k(relevant, ranked, k)
    if precision + recall == 0:
        return 0.0
    return 2 * precision * recall / (precision + recall)


def ndcg_at_k(relevant: Judgments, ranked: Sequence[str], k: int) -> float:
    """Normalized discounted cumulative gain at ``k`` — trec_eval's ``ndcg_cut``.

    Supports graded relevance: a gain of 3 at rank 1 outscores a gain of 1 at rank 1.
    The ideal is taken over every judged-relevant document, including ones the ranker
    never returned, so nDCG cannot be maximised by returning less."""
    require_metrics_extra()
    _validate_at_k(relevant, ranked, k)
    return _score(relevant, ranked, nDCG @ k)


def mrr(relevant: Judgments, ranked: Sequence[str]) -> float:
    """Reciprocal rank of the first relevant document; 0.0 if the list holds none."""
    require_metrics_extra()
    _validate(relevant, ranked)
    return _score(relevant, ranked, RR)


def average_precision(relevant: Judgments, ranked: Sequence[str]) -> float:
    """Average precision over the whole ranked list — trec_eval's ``map``, one query.

    The denominator is the number of documents judged relevant *overall*, not the number
    retrieved, so retrieving 3 of 30 relevant documents flawlessly is AP 0.1 and not AP
    1.0. That is the classical definition, and trec_eval implements it directly."""
    require_metrics_extra()
    _validate(relevant, ranked)
    return _score(relevant, ranked, AP)


def _gains(query: RankedQuery) -> dict[str, float]:
    """A query's judgments as a doc-id map, refusing a document judged twice."""
    gains = {judgment.doc_id: judgment.gain for judgment in query.judgments}
    if len(gains) != len(query.judgments):
        raise InvalidRankingRequest
    return gains


def _require_queries(queries: Sequence[RankedQuery]) -> None:
    if not queries:
        raise InvalidRankingRequest("query set is empty; there is nothing to average over")


def mean_average_precision(queries: Sequence[RankedQuery]) -> float:
    """MAP: the mean of every query's average precision."""
    _require_queries(queries)
    return fmean(average_precision(_gains(q), q.ranked) for q in queries)


def _mean_of(rows: Sequence[QueryRanking], pick: Callable[[QueryRanking], float]) -> float:
    return fmean(pick(row) for row in rows)


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
