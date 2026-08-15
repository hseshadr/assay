"""The ranking face, pinned to hand-computed worked examples.

Every expected number in this file was computed by hand from the metric's definition
(the ``# hand:`` comments show the arithmetic), never read back out of the code under
test. A test that asserts what the implementation happens to return measures shape, not
property, and would stay green through the exact bugs this module exists to catch.
"""

from __future__ import annotations

import numpy as np
import pytest

from assay.errors import EmptyRelevantSet, InvalidRankingRequest
from assay.models import RankedQuery, RelevanceJudgment
from assay.ranking import (
    average_precision,
    binary_judgments,
    f1_at_k,
    mean_average_precision,
    mrr,
    ndcg_at_k,
    precision_at_k,
    ranking_report,
    recall_at_k,
)
from assay.settings import AssaySettings
from assay.uncertainty import Abstention, Interval

# Four judged-relevant documents; the ranker returned five, hitting at positions 1, 3, 5.
_RELEVANT = binary_judgments(["d1", "d3", "d5", "d9"])
_RANKED = ("d1", "d2", "d3", "d4", "d5")

# Graded relevance: a is worth 3, b is worth 2, c is worth 1.
_GRADED = {"a": 3.0, "b": 2.0, "c": 1.0}


# --------------------------------------------------------------------------------------
# precision@k / recall@k / F1@k — set arithmetic over the top-k slice
# --------------------------------------------------------------------------------------


def test_should_count_hits_over_k_when_measuring_precision() -> None:
    # Given five ranked documents with relevant ones at positions 1, 3 and 5
    # When precision is taken at 3 and at 5
    # Then it is the hit count over k
    assert precision_at_k(_RELEVANT, _RANKED, 3) == pytest.approx(2 / 3)  # hand: {d1,d3}/3
    assert precision_at_k(_RELEVANT, _RANKED, 5) == pytest.approx(3 / 5)  # hand: {d1,d3,d5}/5


def test_should_divide_by_the_relevant_set_not_k_when_measuring_recall() -> None:
    # Given four judged-relevant documents, of which the top 3 hold two
    # When recall is taken at 3
    # Then the denominator is the size of the relevant set (4), never k (3)
    assert recall_at_k(_RELEVANT, _RANKED, 3) == pytest.approx(2 / 4)  # hand: 0.5, NOT 2/3
    assert recall_at_k(_RELEVANT, _RANKED, 5) == pytest.approx(3 / 4)  # hand: 0.75, NOT 3/5


def test_should_separate_precision_from_recall_when_relevant_set_is_larger_than_k() -> None:
    # Given 10 relevant documents and a ranker that returned 2, both relevant
    relevant = binary_judgments(f"r{i}" for i in range(10))
    ranked = ("r0", "r1")
    # When both are measured at 2
    # Then precision is perfect and recall is not — the two must not collapse into one
    assert precision_at_k(relevant, ranked, 2) == pytest.approx(1.0)
    assert recall_at_k(relevant, ranked, 2) == pytest.approx(0.2)  # hand: 2/10


def test_should_take_the_harmonic_mean_when_measuring_f1() -> None:
    # Given precision 0.6 and recall 0.75 at k = 5
    # When F1 is taken
    # Then it is 2pr/(p+r), which sits between them and below the arithmetic mean 0.675
    expected = 2 * 0.6 * 0.75 / (0.6 + 0.75)  # hand: 0.9 / 1.35
    assert f1_at_k(_RELEVANT, _RANKED, 5) == pytest.approx(expected)
    assert f1_at_k(_RELEVANT, _RANKED, 5) == pytest.approx(0.6666666666666666)


def test_should_report_zero_f1_when_nothing_relevant_is_retrieved() -> None:
    # Given a ranked list holding none of the relevant documents
    # When F1 is taken
    # Then it is 0.0, not a ZeroDivisionError
    assert f1_at_k(binary_judgments(["z"]), ("a", "b"), 2) == 0.0


def test_should_charge_for_the_empty_positions_when_k_exceeds_the_list() -> None:
    # Given one relevant document and a ranker that returned exactly it
    # When precision is taken at 4 — three positions the ranker left empty
    # Then the denominator stays k (trec_eval's convention): a short list is a real cost,
    # and dividing by the list length would let one good result score 1.0 at k = 10.
    assert precision_at_k(binary_judgments(["a"]), ("a",), 4) == pytest.approx(0.25)
    # Recall is unaffected: it asks a different question and keeps its own denominator.
    assert recall_at_k(binary_judgments(["a"]), ("a",), 4) == pytest.approx(1.0)


# --------------------------------------------------------------------------------------
# nDCG@k — position discount and the ideal
# --------------------------------------------------------------------------------------


def test_should_score_one_when_the_ranking_is_perfect() -> None:
    # Given graded relevance 3 > 2 > 1 returned in exactly that order
    # When nDCG@3 is taken
    # Then it is 1.0 — the ranking IS the ideal
    assert ndcg_at_k(_GRADED, ("a", "b", "c"), 3) == pytest.approx(1.0)


def test_should_score_clearly_below_one_when_the_ranking_is_exactly_reversed() -> None:
    # Given the same graded set returned in exactly the wrong order
    # When nDCG@3 is taken
    # Then it drops well below 1.0, by the position discount alone
    # hand: DCG = 1/log2(2) + 2/log2(3) + 3/log2(4) = 3.761859507142915
    #       IDCG = 3/log2(2) + 2/log2(3) + 1/log2(4) = 4.7618595071429155
    assert ndcg_at_k(_GRADED, ("c", "b", "a"), 3) == pytest.approx(0.7899980042460358)
    assert ndcg_at_k(_GRADED, ("c", "b", "a"), 3) < 0.85


def test_should_rank_a_better_order_above_a_worse_one_when_the_set_is_identical() -> None:
    # Given three orderings of the SAME documents — only position differs
    perfect = ndcg_at_k(_GRADED, ("a", "b", "c"), 3)
    middling = ndcg_at_k(_GRADED, ("b", "a", "c"), 3)
    reversed_ = ndcg_at_k(_GRADED, ("c", "b", "a"), 3)
    # When they are compared
    # Then nDCG strictly orders them. A constant (broken) position discount would make
    # all three equal, because the retrieved SET is the same in all three.
    assert perfect > middling > reversed_


def test_should_penalise_relevant_documents_the_ranker_never_returned() -> None:
    # Given four equally-relevant documents and a ranker that returned only one of them
    relevant = binary_judgments(["a", "b", "c", "d"])
    # When nDCG@4 is taken
    # Then the ideal still counts all four, so one hit cannot score 1.0
    # hand: DCG@4 = 1/log2(2) = 1.0 (positions 2-4 were left empty)
    #       IDCG@4 = 1/log2(2) + 1/log2(3) + 1/log2(4) + 1/log2(5) = 2.5615...
    assert ndcg_at_k(relevant, ("a",), 4) == pytest.approx(0.3903800499921017)


def test_should_reward_putting_the_heavier_grade_first_when_relevance_is_graded() -> None:
    # Given two documents whose grades differ (3 vs 1)
    graded = {"heavy": 3.0, "light": 1.0}
    # When each order is scored at 2
    # Then the graded order wins — binary relevance could not tell these apart
    assert ndcg_at_k(graded, ("heavy", "light"), 2) == pytest.approx(1.0)
    assert ndcg_at_k(graded, ("light", "heavy"), 2) < 1.0


# --------------------------------------------------------------------------------------
# MRR and average precision
# --------------------------------------------------------------------------------------


def test_should_report_the_reciprocal_of_the_first_hit_position() -> None:
    # Given lists whose first relevant document sits at position 1, 3 and nowhere
    # When MRR is taken
    # Then it is 1/position, or 0.0 when the list holds no hit at all
    assert mrr(binary_judgments(["x"]), ("x", "a", "b")) == pytest.approx(1.0)
    assert mrr(binary_judgments(["x"]), ("a", "b", "x")) == pytest.approx(1 / 3)
    assert mrr(binary_judgments(["x"]), ("a", "b")) == 0.0


def test_should_average_precision_over_every_hit_position() -> None:
    # Given relevant documents at ranks 1, 3 and 5 out of 4 judged relevant
    # When average precision is taken
    # Then it averages precision AT EACH HIT over the full relevant set
    # hand: (1/1 + 2/3 + 3/5) / 4 = 0.5666666666666667
    assert average_precision(_RELEVANT, _RANKED) == pytest.approx(0.5666666666666667)


def test_should_divide_average_precision_by_the_full_relevant_set() -> None:
    # Given 4 relevant documents and a ranker that returned one of them, perfectly
    # When average precision is taken
    # Then it is 0.25, not 1.0 — retrieving 1 of 4 flawlessly is not a flawless ranking
    assert average_precision(binary_judgments(["a", "b", "c", "d"]), ("a",)) == pytest.approx(0.25)


def test_should_report_zero_average_precision_when_nothing_relevant_is_retrieved() -> None:
    # Given a ranked list with no relevant document in it
    # When average precision is taken
    # Then it is 0.0 (sklearn scores an all-negative row 1.0; the rescale must kill that)
    assert average_precision(binary_judgments(["z"]), ("a", "b")) == 0.0


def test_should_mean_average_precision_across_a_query_set() -> None:
    # Given two queries whose APs are 1.0 and 0.5 by hand
    queries = (
        _query("perfect", ["a"], ["a", "b"]),  # hand: (1/1)/1 = 1.0
        _query("second", ["a"], ["b", "a"]),  # hand: (1/2)/1 = 0.5
    )
    # When MAP is taken
    # Then it is the mean of the per-query values
    assert mean_average_precision(queries) == pytest.approx(0.75)


# --------------------------------------------------------------------------------------
# Refusals — every one of these would otherwise return a number nobody should believe
# --------------------------------------------------------------------------------------


def test_should_refuse_when_no_document_is_judged_relevant() -> None:
    # Given a query with an empty relevant set
    # When any metric is taken
    # Then it refuses with a coded error rather than returning 0.0, which would read as
    # "the ranker found nothing" and blame the ranker for missing JUDGMENTS.
    with pytest.raises(EmptyRelevantSet) as caught:
        precision_at_k({}, ("a", "b"), 2)
    assert caught.value.code == "assay.empty_relevant_set"
    with pytest.raises(EmptyRelevantSet):
        ndcg_at_k({"a": 0.0, "b": 0.0}, ("a", "b"), 2)


def test_should_refuse_when_k_is_zero_or_negative() -> None:
    # Given a k that names no positions at all
    # When a @k metric is taken
    # Then it refuses — precision over zero positions has no denominator
    for bad_k in (0, -1):
        with pytest.raises(InvalidRankingRequest) as caught:
            precision_at_k(_RELEVANT, _RANKED, bad_k)
        assert caught.value.code == "assay.invalid_ranking_request"
        with pytest.raises(InvalidRankingRequest):
            ndcg_at_k(_RELEVANT, _RANKED, bad_k)
        with pytest.raises(InvalidRankingRequest):
            recall_at_k(_RELEVANT, _RANKED, bad_k)


def test_should_refuse_a_ranked_list_holding_the_same_document_twice() -> None:
    # Given a ranked list with a duplicate id
    # When any metric is taken
    # Then it refuses rather than silently de-duplicating: a duplicate makes "position of
    # the first hit" ambiguous and inflates precision by double-counting one document.
    with pytest.raises(InvalidRankingRequest):
        precision_at_k(_RELEVANT, ("d1", "d1", "d3"), 3)


def test_should_refuse_an_empty_ranked_list() -> None:
    # Given a query that returned nothing
    # When any metric is taken
    # Then it refuses. Scoring it 0.0 would mix "we retrieved nothing" with "we ranked
    # badly" — different failures, different fixes.
    with pytest.raises(InvalidRankingRequest):
        mrr(_RELEVANT, ())


def test_should_refuse_a_negative_relevance_gain() -> None:
    # Given a judgment with a negative gain
    # When a metric is taken
    # Then it refuses — a negative gain has no meaning in discounted cumulative gain
    with pytest.raises(InvalidRankingRequest):
        ndcg_at_k({"a": -1.0, "b": 1.0}, ("a", "b"), 2)


def test_should_refuse_a_fractional_relevance_gain() -> None:
    # Given a judgment graded 2.5 — a relevance LEVEL of two and a half
    # When a metric is taken
    # Then it refuses. trec_eval qrels are integer-graded by definition, and rounding to
    # reach one would decide, silently and unaccountably, whether a 0.5 gain counts as
    # relevant at all. Refusing beats inventing a semantics the reference does not have.
    with pytest.raises(InvalidRankingRequest) as caught:
        ndcg_at_k({"a": 2.5, "b": 1.0}, ("a", "b"), 2)
    assert caught.value.code == "assay.invalid_ranking_request"
    with pytest.raises(InvalidRankingRequest):
        average_precision({"a": 0.5}, ("a", "b"))
    # And whole gains handed over as floats stay accepted — that is the public type
    assert ndcg_at_k({"a": 2.0, "b": 1.0}, ("a", "b"), 2) == pytest.approx(1.0)


def test_should_refuse_a_document_judged_twice_in_one_query() -> None:
    # Given a query whose judgments name the same document twice
    query = RankedQuery(
        query="dupe",
        judgments=(RelevanceJudgment(doc_id="a"), RelevanceJudgment(doc_id="a", gain=3.0)),
        ranked=("a", "b"),
    )
    # When it is scored
    # Then it refuses: which gain applies is undecidable
    with pytest.raises(InvalidRankingRequest):
        ranking_report((query,), settings=AssaySettings())


def test_should_refuse_an_empty_query_set() -> None:
    # Given no queries at all
    # When a report is asked for
    # Then it refuses rather than reporting a mean over nothing
    with pytest.raises(InvalidRankingRequest):
        ranking_report((), settings=AssaySettings())
    with pytest.raises(InvalidRankingRequest):
        mean_average_precision(())


# --------------------------------------------------------------------------------------
# The aggregate report
# --------------------------------------------------------------------------------------


def _query(name: str, relevant: list[str], ranked: list[str]) -> RankedQuery:
    return RankedQuery(
        query=name,
        judgments=tuple(RelevanceJudgment(doc_id=d) for d in relevant),
        ranked=tuple(ranked),
    )


def _query_set(n: int) -> tuple[RankedQuery, ...]:
    """``n`` queries, each returning its one relevant document at position 1."""
    return tuple(_query(f"q{i}", [f"a{i}"], [f"a{i}", f"b{i}"]) for i in range(n))


def test_should_report_every_query_alongside_the_mean() -> None:
    # Given two queries, one perfect and one that buried its hit at position 2
    queries = (_query("hit", ["a"], ["a", "b"]), _query("miss", ["a"], ["b", "a"]))
    # When the set is scored at k = 2
    report = ranking_report(queries, settings=AssaySettings(), k=2)
    # Then every query is listed, so a mean can never hide which one failed
    assert report.k == 2
    assert report.n_queries == 2
    assert tuple(r.query for r in report.per_query) == ("hit", "miss")
    assert report.per_query[0].reciprocal_rank == pytest.approx(1.0)
    assert report.per_query[1].reciprocal_rank == pytest.approx(0.5)
    assert report.mrr == pytest.approx(0.75)  # hand: (1.0 + 0.5) / 2
    assert report.mean_recall_at_k == pytest.approx(1.0)  # both found it within k = 2
    assert report.mean_precision_at_k == pytest.approx(0.5)  # hand: (1/2 + 1/2) / 2


def test_should_default_k_from_settings_when_not_given() -> None:
    # Given settings whose ranking_k is 3
    settings = AssaySettings(ranking_k=3)
    # When a report is asked for without a k
    report = ranking_report(_query_set(2), settings=settings)
    # Then k comes from settings — no hardcoded default in the logic
    assert report.k == 3


def test_should_abstain_on_the_interval_when_there_are_too_few_queries() -> None:
    # Given fewer queries than the sample floor
    settings = AssaySettings(min_samples=30)
    # When the set is scored
    report = ranking_report(_query_set(5), settings=settings, k=2)
    # Then the MEAN is still reported, but its interval abstains — the same honesty floor
    # the classification face uses, not a second uncertainty story.
    assert report.mean_ndcg_at_k == pytest.approx(1.0)
    assert isinstance(report.ndcg_interval, Abstention)
    assert report.ndcg_interval.n_samples == 5
    assert report.ndcg_interval.min_samples == 30


def test_should_return_a_bootstrap_interval_when_above_the_floor() -> None:
    # Given enough queries to support an interval, half of them perfect and half not
    settings = AssaySettings(min_samples=10, bootstrap_resamples=499)
    queries = _query_set(10) + tuple(
        _query(f"bad{i}", [f"x{i}"], [f"y{i}", f"x{i}"]) for i in range(10)
    )
    # When the set is scored
    report = ranking_report(queries, settings=settings, k=2)
    # Then the interval brackets the point estimate
    interval = report.ndcg_interval
    assert isinstance(interval, Interval)
    assert interval.low <= interval.point <= interval.high
    assert interval.point == pytest.approx(report.mean_ndcg_at_k)


# --------------------------------------------------------------------------------------
# Property: every metric is a fraction, and precision@len(ranked) is the plain hit rate
# --------------------------------------------------------------------------------------


def _random_case(rng: np.random.Generator) -> tuple[dict[str, float], tuple[str, ...]]:
    docs = [f"d{i}" for i in range(int(rng.integers(2, 12)))]
    ranked = tuple(rng.permutation(docs)[: int(rng.integers(1, len(docs) + 1))].tolist())
    judged = rng.permutation(docs)[: int(rng.integers(1, len(docs) + 1))].tolist()
    return {d: float(rng.integers(1, 4)) for d in judged}, ranked


def test_should_stay_inside_zero_and_one_for_every_metric_and_every_input() -> None:
    # Given 300 seeded random (relevant set, ranked list, k) cases
    rng = np.random.default_rng(20260803)
    for _ in range(300):
        relevant, ranked = _random_case(rng)
        k = int(rng.integers(1, 15))
        # When every metric is taken
        values = (
            precision_at_k(relevant, ranked, k),
            recall_at_k(relevant, ranked, k),
            f1_at_k(relevant, ranked, k),
            ndcg_at_k(relevant, ranked, k),
            mrr(relevant, ranked),
            average_precision(relevant, ranked),
        )
        # Then every one of them is a fraction
        assert all(0.0 <= v <= 1.0 for v in values), (relevant, ranked, k, values)
        # And precision at the full list length is exactly the hit rate
        hits = len(set(ranked) & {d for d, g in relevant.items() if g > 0})
        assert precision_at_k(relevant, ranked, len(ranked)) == pytest.approx(hits / len(ranked))
